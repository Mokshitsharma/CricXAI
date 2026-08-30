"""Train the CricXAI models from the engineered feature table.

Three models (docs/TRD.md §4):

- ``dismissal_prob`` (M1) — calibrated binary P(wicket on this ball).
- ``dismissal_type`` (M2) — multiclass, conditional on a wicket.
- ``expected_runs`` (M3) — regressor, runs off the bat this ball.

Cross-validation is grouped by ``match_id`` (a match is never split across
folds) — random k-fold would leak within-match context and inflate every
number (docs/RULES.md R-5). The reported metrics come from that grouped CV;
the shipped artifact is then refit on all rows, with M1 isotonic-calibrated
on a held-out group split.

Artifacts per model land in
``data/models/<model_id>/<version>/{model.pkl, meta.json, eval.md,
shap_background.parquet}`` and the active pointer is written to
``data/models/active.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import (
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from app.ml.features import select_features
from app.utils.cricket_constants import DISMISSAL_TYPES
from app.utils.file_io import ensure_dir, read_frame, write_json
from app.utils.logger import get_logger

DEFAULT_INPUT = Path("data/processed/delivery_features.csv")
DEFAULT_MODEL_DIR = Path("data/models")
N_SPLITS = 5
SHAP_BACKGROUND_ROWS = 200
RANDOM_STATE = 42

_CLF_PARAMS = dict(
    n_estimators=500,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=40,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    verbosity=-1,
)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001 - best effort
        return "unknown"


def _data_hash(df: pd.DataFrame) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(df, index=True).values.tobytes()
    ).hexdigest()[:16]


def _version() -> str:
    return f"{datetime.now(UTC):%Y-%m-%d}.{_git_sha()}"


# ---------------------------------------------------------------------------
# M1 — dismissal probability
# ---------------------------------------------------------------------------

def train_dismissal_prob(df: pd.DataFrame, logger) -> dict:
    x, feature_names = select_features(df)
    y = df["will_dismiss"].astype(int).to_numpy()
    groups = df["match_id"].to_numpy()

    oof = np.zeros(len(y), dtype=float)
    gkf = GroupKFold(n_splits=N_SPLITS)
    for fold, (tr, va) in enumerate(gkf.split(x, y, groups), start=1):
        clf = LGBMClassifier(**_CLF_PARAMS)
        clf.fit(x.iloc[tr], y[tr])
        oof[va] = clf.predict_proba(x.iloc[va])[:, 1]
        logger.info("  M1 fold %s/%s done", fold, N_SPLITS)

    base_rate = float(y.mean())
    metrics = {
        "n_rows": int(len(y)),
        "base_rate": base_rate,
        "brier": float(brier_score_loss(y, oof)),
        "brier_baseline": float(np.mean((y - base_rate) ** 2)),
        "log_loss": float(log_loss(y, np.clip(oof, 1e-6, 1 - 1e-6))),
        "roc_auc": float(roc_auc_score(y, oof)),
    }
    metrics["brier_improvement_pct"] = round(
        100.0 * (1.0 - metrics["brier"] / metrics["brier_baseline"]), 2
    )
    metrics["reliability"] = _reliability_bins(y, oof)
    logger.info(
        "  M1 grouped-CV Brier %.5f vs baseline %.5f (%.1f%% better), AUC %.3f",
        metrics["brier"], metrics["brier_baseline"],
        metrics["brier_improvement_pct"], metrics["roc_auc"],
    )

    # Final model: base fit on a group split, isotonic calibration on the holdout.
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=RANDOM_STATE)
    tr, cal = next(gss.split(x, y, groups))
    base = LGBMClassifier(**_CLF_PARAMS).fit(x.iloc[tr], y[tr])
    calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="isotonic")
    calibrated.fit(x.iloc[cal], y[cal])

    return {
        "model": calibrated,
        "base_model": base,
        "feature_names": feature_names,
        "kind": "classifier",
        "metrics": metrics,
        "X": x,
    }


def _reliability_bins(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, n_bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        out.append(
            {
                "bin": f"{lo:.1f}-{hi:.1f}",
                "n": int(mask.sum()),
                "mean_pred": float(p[mask].mean()),
                "observed": float(y[mask].mean()),
            }
        )
    return out


# ---------------------------------------------------------------------------
# M2 — dismissal type
# ---------------------------------------------------------------------------

def train_dismissal_type(df: pd.DataFrame, logger) -> dict:
    wk = df[(df["is_wicket"]) & (df["dismissal_type_encoded"] >= 0)].copy()
    x, feature_names = select_features(wk)
    y = wk["dismissal_type_encoded"].astype(int).to_numpy()
    groups = wk["match_id"].to_numpy()
    classes = sorted(np.unique(y).tolist())

    n_splits = min(N_SPLITS, len(np.unique(groups)))
    oof = np.full(len(y), -1, dtype=int)
    gkf = GroupKFold(n_splits=n_splits)
    for fold, (tr, va) in enumerate(gkf.split(x, y, groups), start=1):
        clf = LGBMClassifier(objective="multiclass", **_CLF_PARAMS)
        clf.fit(x.iloc[tr], y[tr])
        oof[va] = clf.predict(x.iloc[va])
        logger.info("  M2 fold %s/%s done", fold, n_splits)

    metrics = {
        "n_rows": int(len(y)),
        "classes": [DISMISSAL_TYPES[c] for c in classes],
        "macro_f1": float(f1_score(y, oof, average="macro")),
        "accuracy": float((oof == y).mean()),
    }
    logger.info("  M2 grouped-CV macro-F1 %.3f, acc %.3f", metrics["macro_f1"], metrics["accuracy"])

    final = LGBMClassifier(objective="multiclass", **_CLF_PARAMS).fit(x, y)
    return {
        "model": final,
        "feature_names": feature_names,
        "kind": "multiclass",
        "class_labels": [DISMISSAL_TYPES[c] for c in final.classes_.tolist()],
        "metrics": metrics,
        "X": x,
    }


# ---------------------------------------------------------------------------
# M3 — expected runs
# ---------------------------------------------------------------------------

def train_expected_runs(df: pd.DataFrame, logger) -> dict:
    frame = df[~df["is_wicket"]].copy()
    x, feature_names = select_features(frame)
    y = frame["total_runs"].fillna(0).clip(0, 6).to_numpy(dtype=float)
    groups = frame["match_id"].to_numpy()

    oof = np.zeros(len(y), dtype=float)
    gkf = GroupKFold(n_splits=N_SPLITS)
    for fold, (tr, va) in enumerate(gkf.split(x, y, groups), start=1):
        reg = LGBMRegressor(**_CLF_PARAMS)
        reg.fit(x.iloc[tr], y[tr])
        oof[va] = reg.predict(x.iloc[va])
        logger.info("  M3 fold %s/%s done", fold, N_SPLITS)

    metrics = {
        "n_rows": int(len(y)),
        "mean_runs": float(y.mean()),
        "mae": float(mean_absolute_error(y, oof)),
        "rmse": float(np.sqrt(mean_squared_error(y, oof))),
        "mae_baseline": float(mean_absolute_error(y, np.full_like(y, y.mean()))),
    }
    logger.info("  M3 grouped-CV MAE %.3f vs baseline %.3f", metrics["mae"], metrics["mae_baseline"])

    final = LGBMRegressor(**_CLF_PARAMS).fit(x, y)
    return {
        "model": final,
        "feature_names": feature_names,
        "kind": "regressor",
        "metrics": metrics,
        "X": x,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_model(
    model_id: str, result: dict, version: str, model_dir: Path,
    data_hash: str, source: str, logger,
) -> Path:
    import joblib

    out = model_dir / model_id / version
    ensure_dir(out)

    payload = {k: v for k, v in result.items() if k != "X"}
    joblib.dump(payload, out / "model.pkl")

    background = result["X"].sample(
        n=min(SHAP_BACKGROUND_ROWS, len(result["X"])), random_state=RANDOM_STATE
    )
    background.to_parquet(out / "shap_background.parquet")

    meta = {
        "model_id": model_id,
        "version": version,
        "kind": result["kind"],
        "git_sha": _git_sha(),
        "data_snapshot_hash": data_hash,
        "data_source": source,
        "feature_names": result["feature_names"],
        "class_labels": result.get("class_labels"),
        "metrics": result["metrics"],
        "created_at": datetime.now(UTC).isoformat(),
    }
    write_json(meta, out / "meta.json")
    (out / "eval.md").write_text(_eval_markdown(meta), encoding="utf-8")
    logger.info("Saved %s -> %s", model_id, out)
    return out


def _eval_markdown(meta: dict) -> str:
    lines = [
        f"# {meta['model_id']} — {meta['version']}",
        "",
        f"- kind: `{meta['kind']}`",
        f"- git: `{meta['git_sha']}`  data: `{meta['data_snapshot_hash']}`  source: `{meta['data_source']}`",
        f"- created: {meta['created_at']}",
        "",
        "## Metrics (grouped CV by match_id)",
        "",
        "```json",
        json.dumps(meta["metrics"], indent=2),
        "```",
    ]
    return "\n".join(lines)


def _write_active_pointer(model_dir: Path, version: str, saved: dict[str, Path]) -> None:
    active = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "models": {mid: str(path.relative_to(model_dir)) for mid, path in saved.items()},
    }
    write_json(active, model_dir / "active.json")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(input_path: Path, model_dir: Path, logger) -> dict:
    df = read_frame(input_path.with_suffix(""))  # prefers .parquet, falls back to .csv
    df["is_wicket"] = df["is_wicket"].astype(bool)
    source = "mock" if (df.get("source") == "mock").all() else "mixed/real"
    data_hash = _data_hash(df)
    version = _version()
    logger.info("Training on %s rows from %s (source=%s, version=%s)",
                len(df), input_path, source, version)

    results = {
        "dismissal_prob": train_dismissal_prob(df, logger),
        "dismissal_type": train_dismissal_type(df, logger),
        "expected_runs": train_expected_runs(df, logger),
    }

    saved = {
        mid: _save_model(mid, res, version, model_dir, data_hash, source, logger)
        for mid, res in results.items()
    }
    _write_active_pointer(model_dir, version, saved)

    combined = ["# CricXAI models — eval summary", "", f"version: `{version}`  source: `{source}`", ""]
    for mid, res in results.items():
        combined += [f"## {mid}", "```json", json.dumps(res["metrics"], indent=2), "```", ""]
    (model_dir / "EVAL.md").write_text("\n".join(combined), encoding="utf-8")

    return {mid: res["metrics"] for mid, res in results.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train CricXAI models.")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logger = get_logger(__name__)
    stem = args.input.with_suffix("")
    if not stem.with_suffix(".parquet").exists() and not stem.with_suffix(".csv").exists():
        logger.error("Feature table not found: %s[.parquet|.csv] (run build_features first)", stem)
        return 1
    metrics = run(args.input, args.model_dir, logger)
    logger.info("Done. Summary: %s", json.dumps(metrics)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

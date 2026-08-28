"""Load the active model set from disk (or an override directory).

Layout written by ``scripts/train.py``::

    data/models/active.json
    data/models/<model_id>/<version>/model.pkl        # joblib dict
    data/models/<model_id>/<version>/meta.json
    data/models/<model_id>/<version>/shap_background.parquet

``model.pkl`` is a dict with at least ``model``, ``feature_names``, ``kind``;
the ``dismissal_prob`` artifact also carries ``base_model`` (the raw LightGBM
tree for SHAP). The API calls :func:`load_active_models` once at boot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from app.utils.file_io import read_json
from app.utils.logger import get_logger


def _default_model_dir() -> Path:
    return Path(os.environ.get("CRICXAI_MODEL_DIR", "data/models"))


class NoActiveModelError(RuntimeError):
    """Raised when there is no usable active model set (fresh checkout)."""


@dataclass
class LoadedModel:
    model_id: str
    version: str
    kind: str
    estimator: object
    base_model: object | None
    feature_names: list[str]
    class_labels: list[str] | None
    shap_background: pd.DataFrame | None
    meta: dict


@dataclass
class ActiveModels:
    version: str
    dismissal_prob: LoadedModel
    dismissal_type: LoadedModel
    expected_runs: LoadedModel

    def as_dict(self) -> dict[str, LoadedModel]:
        return {
            "dismissal_prob": self.dismissal_prob,
            "dismissal_type": self.dismissal_type,
            "expected_runs": self.expected_runs,
        }


def _load_one(model_dir: Path, model_id: str, rel_path: str, logger) -> LoadedModel:
    path = model_dir / rel_path
    pkl = path / "model.pkl"
    if not pkl.exists():
        raise NoActiveModelError(f"Missing artifact: {pkl}")

    payload = joblib.load(pkl)
    meta = read_json(path / "meta.json") if (path / "meta.json").exists() else {}

    background = None
    bg_path = path / "shap_background.parquet"
    if bg_path.exists():
        try:
            background = pd.read_parquet(bg_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read SHAP background for %s: %s", model_id, exc)

    return LoadedModel(
        model_id=model_id,
        version=meta.get("version", path.name),
        kind=payload.get("kind", "unknown"),
        estimator=payload["model"],
        base_model=payload.get("base_model"),
        feature_names=list(payload["feature_names"]),
        class_labels=payload.get("class_labels") or meta.get("class_labels"),
        shap_background=background,
        meta=meta,
    )


def load_active_models(model_dir: Path | None = None, logger=None) -> ActiveModels:
    logger = logger or get_logger(__name__)
    model_dir = Path(model_dir or _default_model_dir())
    active_file = model_dir / "active.json"
    if not active_file.exists():
        raise NoActiveModelError(
            f"No active.json in {model_dir}. Run `python -m scripts.train` first."
        )

    active = read_json(active_file)
    models = active.get("models", {})
    required = ("dismissal_prob", "dismissal_type", "expected_runs")
    if not all(k in models for k in required):
        raise NoActiveModelError(f"active.json missing one of {required}: {list(models)}")

    loaded = {
        mid: _load_one(model_dir, mid, models[mid], logger) for mid in required
    }
    logger.info("Loaded active models, version %s", active.get("version"))
    return ActiveModels(
        version=active.get("version", "unknown"),
        dismissal_prob=loaded["dismissal_prob"],
        dismissal_type=loaded["dismissal_type"],
        expected_runs=loaded["expected_runs"],
    )

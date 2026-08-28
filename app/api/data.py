"""In-memory, CSV-backed data access layer.

Loads ``deliveries.csv``, ``matches.csv`` and ``delivery_features.csv`` once
at startup and answers the read queries the API needs. The interface
(methods on :class:`DataStore`) is what a Postgres implementation will
implement in Phase 3 — keep it small and storage-agnostic.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.features import BASE_FEATURES, historical_feature_columns
from app.utils.logger import get_logger

DEFAULT_PROCESSED_DIR = Path("data/processed")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", str(name).strip().lower()).strip("-")


class DataStore:
    def __init__(self, processed_dir: Path | None = None, logger=None):
        self.logger = logger or get_logger(__name__)
        self.dir = Path(
            processed_dir
            or os.environ.get("CRICXAI_PROCESSED_DIR")
            or DEFAULT_PROCESSED_DIR
        )
        self.deliveries = pd.read_csv(self.dir / "deliveries.csv")
        self.matches = pd.read_csv(self.dir / "matches.csv")
        self.features = pd.read_csv(self.dir / "delivery_features.csv")
        self.deliveries["is_wicket"] = self.deliveries["is_wicket"].astype(bool)
        self.features["is_wicket"] = self.features["is_wicket"].astype(bool)

        self._hist_cols = historical_feature_columns(self.features)
        self._id_to_name: dict[str, str] = {}
        self._name_to_id: dict[str, str] = {}
        for name in sorted(self.deliveries["batsman"].dropna().unique()):
            pid = f"player-{slugify(name)}"
            self._id_to_name[pid] = name
            self._name_to_id[name] = pid

        self._batsman_ctx = self._precompute_batsman_context()
        self._feature_means = self._precompute_feature_means()
        self.logger.info(
            "DataStore ready: %s deliveries, %s matches, %s batsmen",
            len(self.deliveries), len(self.matches), len(self._id_to_name),
        )

    # -- identity ---------------------------------------------------------
    def resolve_batsman(self, batsman_id: str | None, batsman: str | None) -> str | None:
        if batsman_id and batsman_id in self._id_to_name:
            return self._id_to_name[batsman_id]
        if batsman and batsman in self._name_to_id:
            return batsman
        if batsman:
            pid = f"player-{slugify(batsman)}"
            return self._id_to_name.get(pid)
        return None

    def batsman_id(self, name: str) -> str:
        return self._name_to_id.get(name, f"player-{slugify(name)}")

    # -- batsmen --------------------------------------------------------
    def list_batsmen(self, query: str | None = None, limit: int = 50) -> list[dict]:
        rows = []
        for pid, name in self._id_to_name.items():
            if query and query.lower() not in name.lower():
                continue
            ctx = self._batsman_ctx.get(name, {})
            rows.append(
                {
                    "id": pid,
                    "name": name,
                    "balls": int(ctx.get("balls", 0)),
                    "dismissals": int(ctx.get("dismissals", 0)),
                }
            )
        rows.sort(key=lambda r: r["balls"], reverse=True)
        return rows[:limit]

    def batsman_feature_context(self, name: str) -> dict[str, float]:
        return self._batsman_ctx.get(name, {}).get("features", {})

    def batsman_dismissals(self, name: str) -> int:
        return int(self._batsman_ctx.get(name, {}).get("dismissals", 0))

    def batsman_profile(self, name: str) -> dict:
        ctx = self._batsman_ctx.get(name)
        if ctx is None:
            return {}
        feats = ctx["features"]

        def pull(prefix: str) -> dict[str, float]:
            out = {}
            for col in self._hist_cols:
                if col.startswith(prefix):
                    key = col[len(prefix):-len("_pct")] if col.endswith("_pct") else col[len(prefix):]
                    out[key] = round(float(feats.get(col, 0.0)), 1)
            return out

        wk = self.deliveries[(self.deliveries["batsman"] == name) & self.deliveries["is_wicket"]]
        return {
            "id": self.batsman_id(name),
            "name": name,
            "balls_faced": int(ctx.get("balls", 0)),
            "dismissals": int(ctx.get("dismissals", 0)),
            "matches": int(ctx.get("matches", 0)),
            "low_sample": int(ctx.get("dismissals", 0)) < 6,
            "dismissal_type_pct": pull("hist_dismissal_type_"),
            "ball_length_pct": pull("hist_ball_length_"),
            "ball_line_pct": pull("hist_ball_line_"),
            "phase_average": round(float(feats.get("hist_phase_avg", 0.0)), 1),
            "average_under_pressure": round(float(feats.get("hist_avg_under_pressure", 0.0)), 1),
            "average_normal": round(float(feats.get("hist_avg_normal", 0.0)), 1),
            "dismissal_count_by_type": wk["dismissal_type"].value_counts().to_dict(),
        }

    # -- matches ------------------------------------------------------
    def list_matches(self, limit: int = 100) -> list[dict]:
        cols = [c for c in ["match_id", "teams", "venue", "date", "result",
                            "innings1_runs", "innings2_runs", "delivery_count"]
                if c in self.matches.columns]
        return self.matches[cols].head(limit).to_dict(orient="records")

    def match_timeline(self, match_id: str) -> list[dict]:
        d = self.deliveries[self.deliveries["match_id"] == match_id].copy()
        if d.empty:
            return []
        d = d.sort_values(["innings", "over", "ball_in_over"], kind="stable")
        cols = ["innings", "over", "ball_in_over", "batsman", "bowler",
                "total_runs", "outcome", "is_wicket", "dismissal_type",
                "ball_length", "ball_line", "text"]
        return d[[c for c in cols if c in d.columns]].to_dict(orient="records")

    # -- model reasons ------------------------------------------------
    def feature_means(self) -> dict[str, float]:
        return self._feature_means

    # -- internals --------------------------------------------------------
    def _precompute_batsman_context(self) -> dict[str, dict]:
        feat_cols = [c for c in BASE_FEATURES if c in self.features.columns] + self._hist_cols
        out: dict[str, dict] = {}
        grouped_feats = self.features.groupby("batsman")
        deliv = self.deliveries
        for name, g in grouped_feats:
            means = g[feat_cols].mean(numeric_only=True).to_dict()
            dg = deliv[deliv["batsman"] == name]
            out[str(name)] = {
                "features": {k: float(v) for k, v in means.items() if not np.isnan(v)},
                "balls": int((dg["outcome"] != "wide").sum()),
                "dismissals": int(dg["is_wicket"].sum()),
                "matches": int(dg["match_id"].nunique()),
            }
        return out

    def _precompute_feature_means(self) -> dict[str, float]:
        cols = [c for c in BASE_FEATURES if c in self.features.columns] + self._hist_cols
        means = self.features[cols].mean(numeric_only=True)
        return {k: float(v) for k, v in means.items() if not np.isnan(v)}


@lru_cache(maxsize=1)
def get_data_store() -> DataStore:
    return DataStore()

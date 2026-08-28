"""Glue between the HTTP layer, the data store and the recommendation engine."""

from __future__ import annotations

from app.api.data import DataStore
from app.engine.recommend import recommend, score_grid
from app.ml.registry import ActiveModels
from app.utils.cricket_constants import BALL_LENGTH_ENCODING, BALL_LINE_ENCODING, phase_from_over

TOTAL_OVERS = 50
BALLS_PER_OVER = 6
PRESSURE_CAP = 10.0
PRESSURE_WICKET_WEIGHT = 2.0


def compute_pressure_index(
    innings: int, over: int, ball_in_over: int, score: int, wickets: int, target: int | None
) -> float:
    if innings != 2 or target is None:
        return 0.0
    overs_completed = over + max(ball_in_over - 1, 0) / BALLS_PER_OVER
    overs_remaining = max(TOTAL_OVERS - overs_completed, 0.01)
    crr = score / overs_completed if overs_completed > 0 else 0.0
    rrr = (target - score) / overs_remaining
    raw = (rrr - crr) + (wickets / 10.0) * PRESSURE_WICKET_WEIGHT
    return float(min(max(raw, 0.0), PRESSURE_CAP))


class RecommendationService:
    def __init__(self, store: DataStore, models: ActiveModels):
        self.store = store
        self.models = models
        self._feature_means = store.feature_means()

    def _resolve(self, req) -> tuple[str, dict, int, dict, float, str]:
        name = self.store.resolve_batsman(req.batsman_id, req.batsman)
        if name is None:
            raise LookupError("unknown batsman")
        ctx = self.store.batsman_feature_context(name)
        if not ctx:
            raise ValueError("no historical data for this batsman")
        n_dismissals = self.store.batsman_dismissals(name)
        m = req.match
        pressure = compute_pressure_index(
            m.innings, m.over, m.ball_in_over, m.score, m.wickets, m.target
        )
        phase = phase_from_over(m.over)
        situation = {
            "innings": m.innings, "over": m.over, "ball_in_over": m.ball_in_over,
            "score": m.score, "wickets": m.wickets,
            "pressure_index": pressure, "phase": phase,
        }
        return name, ctx, n_dismissals, situation, pressure, phase

    def grid(self, req) -> dict:
        name, ctx, n_dismissals, situation, pressure, phase = self._resolve(req)
        cells = score_grid(
            situation=situation, batsman_features=ctx,
            bowler_type=req.bowler_type, models=self.models,
        )
        return {
            "model_version": self.models.version,
            "situation": {
                "phase": phase, "pressure_index": round(pressure, 2),
                "low_sample": n_dismissals < 6, "batsman": name,
                "bowler_type": req.bowler_type,
            },
            "cells": cells,
        }

    def recommend(self, req, logger=None) -> dict:
        name, ctx, n_dismissals, situation, pressure, phase = self._resolve(req)

        recs = recommend(
            situation=situation,
            batsman_features=ctx,
            bowler_type=req.bowler_type,
            models=self.models,
            feature_means=self._feature_means,
            n_dismissals=n_dismissals,
            top_k=req.options.top_k,
            logger=logger,
        )

        return {
            "model_version": self.models.version,
            "situation": {
                "phase": phase,
                "pressure_index": round(pressure, 2),
                "low_sample": n_dismissals < 6,
                "batsman": name,
                "bowler_type": req.bowler_type,
            },
            "recommendations": [
                {
                    "rank": r.rank,
                    "length": r.length,
                    "line": r.line,
                    "label": f"{r.length.title()}, {r.line.replace('_', ' ')}",
                    "dismissal_probability": r.dismissal_probability,
                    "dismissal_type_top": r.dismissal_type_top,
                    "dismissal_type_distribution": r.dismissal_type_distribution,
                    "expected_runs": r.expected_runs,
                    "field_preset": r.field_preset,
                    "field_label": r.field_label,
                    "field_positions": r.field_positions,
                    "reasons": r.reasons,
                    "confidence": r.confidence,
                    "score": r.score,
                }
                for r in recs
            ],
        }

    def predict_dismissal(self, req, logger=None) -> dict:
        name = self.store.resolve_batsman(req.batsman_id, req.batsman)
        if name is None:
            raise LookupError("unknown batsman")
        if req.length not in BALL_LENGTH_ENCODING or req.line not in BALL_LINE_ENCODING:
            raise ValueError("invalid length or line")

        # Score the whole grid so the requested delivery is always present.
        full = self.recommend(_SingleCandidateRequest(req, top_k=64), logger=logger)
        for rec in full["recommendations"]:
            if rec["length"] == req.length and rec["line"] == req.line:
                return {"model_version": full["model_version"],
                        "situation": full["situation"], "prediction": rec}
        raise ValueError("requested length/line is not a plausible delivery for this bowler type")


class _SingleCandidateRequest:
    """Adapt a DismissalPredictRequest to the RecommendationRequest shape."""

    def __init__(self, req, top_k: int):
        self.match = req.match
        self.batsman_id = req.batsman_id
        self.batsman = req.batsman
        self.bowler_type = req.bowler_type

        class _Opt:
            pass

        self.options = _Opt()
        self.options.top_k = top_k

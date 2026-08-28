"""Score the candidate delivery grid and return the top-k ranked options.

Given a match situation and a batsman's (leakage-free) feature context, for
a fixed bowler type:

1. build the candidate grid (``candidates.candidate_grid``),
2. score every candidate with M1 (P wicket) and M3 (E runs),
3. rank by the phase objective (``objective.score_candidate``),
4. for the top-k: M2 dismissal-type distribution, SHAP-derived reasons, a
   heuristic field, and a confidence label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.engine.candidates import candidate_grid
from app.engine.field import choose_field
from app.engine.objective import score_candidate
from app.engine.reasons import build_reasons
from app.ml.explain import shap_contributions
from app.ml.features import select_features
from app.ml.registry import ActiveModels
from app.utils.cricket_constants import PHASE_ENCODING, phase_from_over

_LOW_SAMPLE_DISMISSALS = 6
_CONFIDENT_DISMISSALS = 15
_LOW_SAMPLE_PENALTY = 0.02

# Feature columns the caller may not supply; defaulted to a neutral value.
_ROLLING_DEFAULTS = {
    "batsman_runs_so_far": 0.0,
    "batsman_balls_faced": 0.0,
    "batsman_strike_rate": 0.0,
    "batsman_dot_pct": 0.0,
    "bowler_balls_bowled": 0.0,
    "bowler_wickets_so_far": 0.0,
    "bowler_economy": 0.0,
}


@dataclass
class Recommendation:
    rank: int
    length: str
    line: str
    dismissal_probability: float
    dismissal_type_top: str
    dismissal_type_distribution: dict[str, float]
    expected_runs: float
    field_preset: str
    field_label: str
    field_positions: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: str = "unknown"
    score: float = 0.0


def _confidence(n_dismissals: int, margin: float) -> str:
    if n_dismissals >= _CONFIDENT_DISMISSALS and margin >= 0.008:
        return "high"
    if n_dismissals >= _LOW_SAMPLE_DISMISSALS:
        return "medium"
    return "low"


def _base_row(situation: dict, batsman_features: dict) -> dict:
    over = int(situation.get("over", 0))
    phase = situation.get("phase") or phase_from_over(over)
    row: dict[str, float] = dict(_ROLLING_DEFAULTS)
    row.update({k: float(v) for k, v in batsman_features.items() if isinstance(v, (int, float))})
    row.update(
        {
            "innings": float(situation.get("innings", 1)),
            "over": float(over),
            "phase_encoded": float(PHASE_ENCODING.get(phase, 0)),
            "innings_score": float(situation.get("score", situation.get("innings_score", 0))),
            "innings_wickets": float(situation.get("wickets", situation.get("innings_wickets", 0))),
            "pressure_index": float(situation.get("pressure_index", 0.0)),
        }
    )
    # Allow explicit rolling overrides from the caller.
    for key in _ROLLING_DEFAULTS:
        if key in situation and situation[key] is not None:
            row[key] = float(situation[key])
    return row, phase


def score_grid(
    *,
    situation: dict,
    batsman_features: dict,
    bowler_type: str,
    models: ActiveModels,
) -> list[dict]:
    """Every candidate delivery scored with M1/M3 — no SHAP, field or reasons.

    Fast enough to drive a live length x line heatmap on every situation edit.
    """
    grid = candidate_grid(bowler_type)
    base, _phase = _base_row(situation, batsman_features)
    frame = pd.DataFrame([base] * len(grid))
    frame["ball_length_encoded"] = [c.length_encoded for c in grid]
    frame["ball_line_encoded"] = [c.line_encoded for c in grid]

    x1, _ = select_features(frame, models.dismissal_prob.feature_names)
    p_wicket = models.dismissal_prob.estimator.predict_proba(x1)[:, 1]
    x3, _ = select_features(frame, models.expected_runs.feature_names)
    e_runs = np.clip(models.expected_runs.estimator.predict(x3), 0.0, 6.0)

    return [
        {
            "length": c.length,
            "line": c.line,
            "dismissal_probability": round(float(p), 4),
            "expected_runs": round(float(r), 2),
        }
        for c, p, r in zip(grid, p_wicket, e_runs, strict=True)
    ]


def recommend(
    *,
    situation: dict,
    batsman_features: dict,
    bowler_type: str,
    models: ActiveModels,
    feature_means: dict[str, float] | None = None,
    n_dismissals: int = 0,
    top_k: int = 3,
    logger=None,
) -> list[Recommendation]:
    grid = candidate_grid(bowler_type)
    base, phase = _base_row(situation, batsman_features)

    frame = pd.DataFrame([base] * len(grid))
    frame["ball_length_encoded"] = [c.length_encoded for c in grid]
    frame["ball_line_encoded"] = [c.line_encoded for c in grid]

    x1, _ = select_features(frame, models.dismissal_prob.feature_names)
    p_wicket = models.dismissal_prob.estimator.predict_proba(x1)[:, 1]

    x3, _ = select_features(frame, models.expected_runs.feature_names)
    e_runs = np.clip(models.expected_runs.estimator.predict(x3), 0.0, 6.0)

    penalty = _LOW_SAMPLE_PENALTY if n_dismissals < _LOW_SAMPLE_DISMISSALS else 0.0
    scores = np.array(
        [score_candidate(p, r, phase, penalty) for p, r in zip(p_wicket, e_runs, strict=True)]
    )
    order = np.argsort(scores)[::-1][:top_k]
    margin = float(p_wicket[order[0]] - np.median(p_wicket))
    confidence = _confidence(n_dismissals, margin)

    x2, _ = select_features(frame, models.dismissal_type.feature_names)
    dt_labels = models.dismissal_type.class_labels or []

    recs: list[Recommendation] = []
    for rank, idx in enumerate(order, start=1):
        cand = grid[idx]

        dt_dist: dict[str, float] = {}
        dt_top = "unknown"
        if dt_labels:
            proba = models.dismissal_type.estimator.predict_proba(x2.iloc[[idx]])[0]
            dt_dist = {lbl: round(float(pr), 4) for lbl, pr in zip(dt_labels, proba, strict=False)}
            dt_top = max(dt_dist, key=dt_dist.get)

        contributions = shap_contributions(
            models.dismissal_prob, x1.iloc[[idx]], logger=logger
        )
        reasons = build_reasons(
            contributions,
            context={
                "phase": phase,
                "length": cand.length,
                "line": cand.line,
                "pressure_index": base["pressure_index"],
                "batsman_strike_rate": base["batsman_strike_rate"],
                "batsman_dot_pct": base["batsman_dot_pct"],
            },
            feature_means=feature_means,
        )

        fld = choose_field(phase, cand.length, cand.line, bowler_type)
        recs.append(
            Recommendation(
                rank=rank,
                length=cand.length,
                line=cand.line,
                dismissal_probability=round(float(p_wicket[idx]), 4),
                dismissal_type_top=dt_top,
                dismissal_type_distribution=dt_dist,
                expected_runs=round(float(e_runs[idx]), 2),
                field_preset=fld["preset"],
                field_label=fld["label"],
                field_positions=fld["positions"],
                reasons=reasons,
                confidence=confidence,
                score=round(float(scores[idx]), 4),
            )
        )
    return recs

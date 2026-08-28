"""Canonical model feature set.

The model consumes the situation *and* the candidate delivery it is being
asked to evaluate (``ball_length_encoded`` / ``ball_line_encoded``). At
training time those are the delivery that was actually bowled; at serving
time the recommendation engine sweeps them across the candidate grid.

Some ``hist_*`` columns are data-dependent (built from the ball lengths /
lines that appear in wicket rows), so the exact ordered feature list is
discovered from the training frame and persisted with each model artifact
(docs/RULES.md R-15). ``select_features`` re-validates that list at serve
time.
"""

from __future__ import annotations

import pandas as pd

# Situation + candidate-delivery features, always present.
BASE_FEATURES: list[str] = [
    "innings",
    "over",
    "phase_encoded",
    "batsman_runs_so_far",
    "batsman_balls_faced",
    "batsman_strike_rate",
    "batsman_dot_pct",
    "bowler_balls_bowled",
    "bowler_wickets_so_far",
    "bowler_economy",
    "innings_score",
    "innings_wickets",
    "pressure_index",
    "ball_length_encoded",
    "ball_line_encoded",
]

# Columns that describe the delivery being evaluated (varied by the engine).
CANDIDATE_FEATURES: list[str] = ["ball_length_encoded", "ball_line_encoded"]


def historical_feature_columns(df: pd.DataFrame) -> list[str]:
    """The ``hist_*`` columns present in this frame, in a stable order."""
    return sorted(c for c in df.columns if c.startswith("hist_"))


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Full ordered feature list for a training frame."""
    return BASE_FEATURES + historical_feature_columns(df)


def select_features(
    df: pd.DataFrame, feature_names: list[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Return ``(X, feature_names)``.

    If ``feature_names`` is given (serving from a persisted artifact), it is
    validated against ``df`` and any missing column is filled with 0.0 so a
    model trained on a richer dataset still scores. If omitted (training),
    the list is derived from ``df``.
    """
    if feature_names is None:
        feature_names = feature_columns(df)

    missing = [c for c in feature_names if c not in df.columns]
    frame = df.copy()
    for col in missing:
        frame[col] = 0.0

    x = frame[feature_names].astype("float64").fillna(0.0)
    return x, feature_names

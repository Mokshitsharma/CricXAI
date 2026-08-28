"""Guards for the leakage invariants in docs/RULES.md (R-1..R-6).

These run on synthetic data only and must stay green in CI.
"""

from __future__ import annotations

import numpy as np

from scripts import build_features, mock_data

KEYS = ["match_id", "innings", "over", "ball_in_over"]
HIST_PREFIX = "hist_"
ROLLING_CONTEXT_COLS = [
    "batsman_runs_so_far", "batsman_balls_faced", "batsman_strike_rate", "batsman_dot_pct",
    "bowler_balls_bowled", "bowler_wickets_so_far", "bowler_economy",
    "innings_score", "innings_wickets", "pressure_index",
]


def test_single_match_has_zero_historical_features():
    deliveries, _ = mock_data.generate(num_matches=1, seed=5)
    feats = build_features.build_features(deliveries)
    hist_cols = [c for c in feats.columns if c.startswith(HIST_PREFIX)]
    assert hist_cols
    # every historical aggregate excludes the row's own match -> nothing left
    assert np.allclose(feats[hist_cols].to_numpy(dtype=float), 0.0)


def test_perturbing_a_ball_outcome_does_not_change_other_rows_situation_features():
    deliveries, _ = mock_data.generate(num_matches=4, seed=6)
    base = build_features.build_features(deliveries.copy())

    perturbed = deliveries.copy().reset_index(drop=True)
    last = perturbed.index[-1]
    perturbed.loc[last, "is_wicket"] = not bool(perturbed.loc[last, "is_wicket"])
    perturbed.loc[last, "total_runs"] = 99
    perturbed.loc[last, "outcome"] = "six"
    changed = build_features.build_features(perturbed)

    perturbed_key = tuple(deliveries.reset_index(drop=True).loc[last, KEYS])

    merged = base.merge(changed, on=KEYS, suffixes=("_base", "_new"))
    others = merged[~(merged[KEYS].apply(tuple, axis=1) == perturbed_key)]

    for col in ROLLING_CONTEXT_COLS:
        b = others[f"{col}_base"].to_numpy(dtype=float)
        n = others[f"{col}_new"].to_numpy(dtype=float)
        assert np.allclose(b, n, equal_nan=True), f"{col} changed for unrelated rows"


def test_rolling_features_start_at_zero_for_first_ball_faced():
    deliveries, _ = mock_data.generate(num_matches=2, seed=8)
    feats = build_features.build_features(deliveries)
    first_balls = feats.sort_values(KEYS).groupby(["match_id", "innings", "batsman"]).head(1)
    assert (first_balls["batsman_balls_faced"] == 0).all()
    assert (first_balls["batsman_runs_so_far"] == 0).all()

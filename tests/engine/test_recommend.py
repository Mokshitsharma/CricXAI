"""Recommendation engine behaviour."""

from __future__ import annotations

import pandas as pd

from app.engine.candidates import candidate_grid
from app.engine.objective import score_candidate
from app.engine.recommend import recommend


def _batsman_ctx(features: pd.DataFrame, deliveries: pd.DataFrame) -> tuple[dict, str, int]:
    outs = deliveries[deliveries["is_wicket"]].groupby("batsman").size().sort_values()
    name = outs.index[-1]  # the batsman with the most dismissals
    n = int(outs.iloc[-1])
    ctx = (
        features[features["batsman"] == name]
        .select_dtypes("number")
        .mean()
        .to_dict()
    )
    return ctx, name, n


def test_grid_excludes_implausible():
    spin = candidate_grid("off_spin")
    assert all(c.length != "bouncer" for c in spin)
    assert all(c.line != "wide_down_leg" for c in spin)
    pace = candidate_grid("pace_right_arm")
    assert len(pace) > len(spin)


def test_objective_prefers_wickets_at_death():
    high_wkt = score_candidate(0.10, 1.5, "death")
    low_wkt = score_candidate(0.04, 1.5, "death")
    assert high_wkt > low_wkt


def test_recommend_shape_and_ordering(active_models, trained_env):
    ctx, _, n = _batsman_ctx(trained_env["features"], trained_env["deliveries"])
    recs = recommend(
        situation={"innings": 2, "over": 44, "score": 260, "wickets": 6, "pressure_index": 6.0},
        batsman_features=ctx,
        bowler_type="pace_right_arm",
        models=active_models,
        n_dismissals=n,
        top_k=3,
    )
    assert len(recs) == 3
    assert [r.rank for r in recs] == [1, 2, 3]
    assert recs[0].score >= recs[1].score >= recs[2].score
    for r in recs:
        assert 0.0 <= r.dismissal_probability <= 1.0
        assert r.reasons
        assert r.field_positions
        assert r.confidence in {"high", "medium", "low"}


def test_low_sample_flips_confidence(active_models, trained_env):
    ctx, _, _ = _batsman_ctx(trained_env["features"], trained_env["deliveries"])
    recs = recommend(
        situation={"innings": 1, "over": 5, "score": 30, "wickets": 1},
        batsman_features=ctx,
        bowler_type="off_spin",
        models=active_models,
        n_dismissals=2,
        top_k=2,
    )
    assert all(r.confidence == "low" for r in recs)

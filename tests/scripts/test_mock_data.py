"""Tests for the deterministic mock ODI generator."""

from __future__ import annotations

import pandas as pd

from scripts import mock_data

_PARSER_COLUMNS = {
    "match_id", "innings", "over", "ball_in_over", "batsman", "bowler",
    "text", "total_runs", "ball_length", "ball_line", "shot_type",
    "outcome", "is_wicket", "dismissal_type", "player_out",
}


def test_generation_is_deterministic():
    d1, m1 = mock_data.generate(num_matches=5, seed=99)
    d2, m2 = mock_data.generate(num_matches=5, seed=99)
    pd.testing.assert_frame_equal(d1, d2)
    pd.testing.assert_frame_equal(m1, m2)


def test_different_seed_differs():
    d1, _ = mock_data.generate(num_matches=5, seed=1)
    d2, _ = mock_data.generate(num_matches=5, seed=2)
    assert not d1.equals(d2)


def test_schema_matches_parser_output():
    deliveries, matches = mock_data.generate(num_matches=4, seed=3)
    assert _PARSER_COLUMNS.issubset(set(deliveries.columns))
    assert (deliveries["source"] == "mock").all()
    assert (matches["series_id"] == mock_data.SERIES_ID).all()


def test_value_ranges_and_consistency():
    deliveries, matches = mock_data.generate(num_matches=8, seed=42)

    assert deliveries["innings"].isin([1, 2]).all()
    assert deliveries["over"].between(0, 49).all()
    assert deliveries["ball_in_over"].between(1, 8).all()
    assert deliveries["total_runs"].between(0, 6).all()
    assert deliveries.loc[deliveries["is_wicket"], "dismissal_type"].notna().all()
    assert deliveries.loc[~deliveries["is_wicket"], "dismissal_type"].isna().all()

    # every wicket row's dismissal type is in the shared vocabulary
    from app.utils.cricket_constants import DISMISSAL_TYPES

    wk_types = set(deliveries.loc[deliveries["is_wicket"], "dismissal_type"].unique())
    assert wk_types.issubset(set(DISMISSAL_TYPES))

    # a full innings never loses more than 10 wickets
    per_innings = deliveries.groupby(["match_id", "innings"])["is_wicket"].sum()
    assert per_innings.max() <= 10

    # match metadata line count matches the delivery rows
    counts = deliveries.groupby("match_id").size()
    for _, row in matches.iterrows():
        assert row["delivery_count"] == counts[row["match_id"]]


def test_batsmen_accumulate_dismissals_across_matches():
    deliveries, _ = mock_data.generate(num_matches=40, seed=11)
    outs = deliveries[deliveries["is_wicket"]].groupby("batsman").size()
    # with 40 matches most frontline batters have several dismissals
    assert (outs >= 3).sum() >= 20

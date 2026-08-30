"""Tests for the Cricsheet ODI ingester — synthetic match dicts, no network."""

from __future__ import annotations

from scripts import build_features, cricsheet_ingest

_PARSER_COLUMNS = {
    "match_id", "innings", "over", "ball_in_over", "batsman", "bowler",
    "text", "total_runs", "ball_length", "ball_line", "shot_type",
    "outcome", "is_wicket", "dismissal_type", "player_out",
}


def _match(match_id="9001", teams=("India", "Australia")):
    return {
        "meta": {"data_version": "1.2.0"},
        "info": {
            "match_type": "ODI",
            "gender": "male",
            "balls_per_over": 6,
            "overs": 50,
            "teams": list(teams),
            "dates": ["2023-03-17"],
            "venue": "Test Ground",
            "event": {"name": "Synthetic Series"},
            "outcome": {"winner": teams[0], "by": {"runs": 40}},
        },
        "innings": [
            {
                "team": teams[0],
                "overs": [
                    {"over": 0, "deliveries": [
                        {"batter": "A", "bowler": "X", "non_striker": "B",
                         "runs": {"batter": 1, "extras": 0, "total": 1}},
                        {"batter": "B", "bowler": "X", "non_striker": "A",
                         "runs": {"batter": 0, "extras": 1, "total": 1},
                         "extras": {"wides": 1}},
                        {"batter": "B", "bowler": "X", "non_striker": "A",
                         "runs": {"batter": 0, "extras": 0, "total": 0},
                         "wickets": [{"kind": "bowled", "player_out": "B"}]},
                        {"batter": "C", "bowler": "X", "non_striker": "A",
                         "runs": {"batter": 4, "extras": 0, "total": 4}},
                    ]},
                ],
            },
            {
                "team": teams[1],
                "overs": [
                    {"over": 0, "deliveries": [
                        {"batter": "P", "bowler": "Y", "non_striker": "Q",
                         "runs": {"batter": 0, "extras": 0, "total": 0}},
                        {"batter": "P", "bowler": "Y", "non_striker": "Q",
                         "runs": {"batter": 0, "extras": 0, "total": 0},
                         "wickets": [{"kind": "caught and bowled", "player_out": "P"}]},
                        {"batter": "Q", "bowler": "Y", "non_striker": "R",
                         "runs": {"batter": 0, "extras": 0, "total": 0},
                         "wickets": [{"kind": "retired hurt", "player_out": "Q"}]},
                    ]},
                ],
            },
        ],
    }


def test_parse_match_schema_and_values():
    rows, meta = cricsheet_ingest.parse_match(_match(), "9001")
    cols = set(rows[0])
    assert _PARSER_COLUMNS.issubset(cols)
    assert all(r["source"] == "cricsheet" for r in rows)
    assert all(r["ball_length"] == "unknown" for r in rows)

    # wide is its own outcome; ball_in_over counts every delivery in the over
    outcomes = [(r["over"], r["ball_in_over"], r["outcome"]) for r in rows if r["innings"] == 1]
    assert (0, 2, "wide") in outcomes
    assert (0, 3, "wicket") in outcomes
    assert (0, 4, "four") in outcomes

    # "caught and bowled" folds into "caught"; "retired hurt" is not a wicket
    inn2 = [r for r in rows if r["innings"] == 2]
    assert inn2[1]["is_wicket"] and inn2[1]["dismissal_type"] == "caught"
    assert not inn2[2]["is_wicket"]

    assert meta["match_id"] == "9001"
    assert meta["result"] == "India won by 40 runs"
    assert meta["innings1_runs"] == 6
    assert meta["delivery_count"] == len(rows)


def test_keep_match_filters():
    keep = cricsheet_ingest._keep_match
    odi = _match()["info"]
    assert keep(odi, "male", None, False)
    assert not keep(odi, "female", None, False)
    assert not keep({**odi, "match_type": "T20"}, "male", None, False)
    assert not keep(odi, "male", "2025-01-01", False)  # match is 2023
    assert not keep({**odi, "teams": ["India", "Nepal"]}, "male", None, True)
    assert keep(odi, "male", None, True)  # India vs Australia


def test_ingest_output_feeds_build_features():
    import pandas as pd

    rows_a, meta_a = cricsheet_ingest.parse_match(_match("1", ("India", "England")), "1")
    rows_b, meta_b = cricsheet_ingest.parse_match(_match("2", ("India", "England")), "2")
    deliveries = pd.DataFrame(rows_a + rows_b)
    feats = build_features.build_features(deliveries)
    assert len(feats) == len(deliveries)
    # historical columns exist and are leakage-free across the 2 synthetic matches
    assert [c for c in feats.columns if c.startswith("hist_")]

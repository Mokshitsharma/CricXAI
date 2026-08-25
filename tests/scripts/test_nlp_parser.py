import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.nlp_parser import (
    extract_dismissal,
    extract_outcome,
    extract_signals,
    parse_delivery,
    parse_match_file,
    parse_matches_dir,
)


def test_extract_signals_matches_length_line_and_shot():
    text = "Fuller delivery outside off stump, Kohli drives hard through covers for four"
    signals = extract_signals(text)
    assert signals["ball_length"] == "full"
    assert signals["ball_line"] == "outside_off"
    assert signals["shot_type"] == "cover_drive"


def test_extract_signals_short_pitched_pull_wicket():
    text = "Short pitched delivery, top-edges the pull shot, taken at fine leg. Kohli out!"
    signals = extract_signals(text)
    assert signals["ball_length"] == "short"
    assert signals["shot_type"] == "pull"


def test_extract_signals_unknown_when_no_phrase_matches():
    signals = extract_signals("The umpire checks his shoelaces.")
    assert signals["ball_length"] == "unknown"
    assert signals["ball_line"] == "unknown"
    assert signals["shot_type"] == "unknown"


def test_extract_outcome_prefers_numeric_runs_over_text():
    assert extract_outcome("Driven for a boundary", total_runs=4, is_wicket=False) == "four"
    assert extract_outcome("Nothing there", total_runs=0, is_wicket=False) == "dot"


def test_extract_outcome_falls_back_to_phrase_when_no_numeric_runs():
    assert extract_outcome("Six! Into the stands", total_runs=None, is_wicket=False) == "six"


def test_extract_outcome_wicket_takes_priority():
    assert extract_outcome("Bowled him!", total_runs=0, is_wicket=True) == "wicket"


def test_extract_dismissal_none_when_not_wicket():
    assert extract_dismissal("Driven for four", None, is_wicket=False) is None


def test_extract_dismissal_bowled():
    text = "Beaten all ends up, bowled him through the gate!"
    assert extract_dismissal(text, None, is_wicket=True) == "bowled"


def test_extract_dismissal_does_not_false_positive_on_short_tokens():
    # A "basic delivery" description should never be misread as "bowled"/"caught"
    # just because it contains loose letters like "b" or "c".
    text = "A basic, comfortable delivery, no drama here"
    assert extract_dismissal(text, None, is_wicket=True) == "unknown"


def test_parse_delivery_full_record():
    record = {
        "inningNumber": 1,
        "overNumber": 8,
        "ballNumber": 3,
        "batsmanName": "Virat Kohli",
        "bowlerName": "Trent Boult",
        "text": "Fuller delivery outside off stump, Kohli drives hard through covers for four",
        "totalRuns": 4,
        "isWicket": False,
    }
    row = parse_delivery(record, match_id="12345")
    assert row["match_id"] == "12345"
    assert row["over"] == 8
    assert row["ball_in_over"] == 3
    assert row["batsman"] == "Virat Kohli"
    assert row["bowler"] == "Trent Boult"
    assert row["outcome"] == "four"
    assert row["ball_length"] == "full"
    assert row["is_wicket"] is False
    assert row["dismissal_type"] is None


def test_parse_delivery_wicket_record():
    record = {
        "inningNumber": 1,
        "overNumber": 12,
        "ballNumber": 5,
        "batsmanName": "Virat Kohli",
        "bowlerName": "Mitchell Starc",
        "text": "Short pitched delivery, top-edges the pull shot, taken at fine leg. Kohli out!",
        "totalRuns": 0,
        "isWicket": True,
        "playerOut": "Virat Kohli",
    }
    row = parse_delivery(record, match_id="12345")
    assert row["is_wicket"] is True
    assert row["dismissal_type"] == "caught"
    assert row["player_out"] == "Virat Kohli"


def test_parse_delivery_handles_missing_fields_gracefully():
    row = parse_delivery({"text": "Some commentary with no structured fields"}, match_id="99")
    assert row["over"] is None
    assert row["ball_in_over"] is None
    assert row["batsman"] is None
    assert row["is_wicket"] is False


def test_parse_delivery_nested_name_objects():
    record = {
        "over": 1,
        "ball": 1,
        "batsman": {"name": "Rohit Sharma"},
        "bowler": {"name": "Josh Hazlewood"},
        "text": "defends solidly, no run",
        "totalRuns": 0,
    }
    row = parse_delivery(record, match_id="1")
    assert row["batsman"] == "Rohit Sharma"
    assert row["bowler"] == "Josh Hazlewood"
    assert row["outcome"] == "dot"


def test_parse_delivery_returns_none_for_non_dict():
    assert parse_delivery("not a dict", match_id="1") is None


def test_parse_match_file_and_directory(tmp_path: Path):
    match_json = {
        "match_id": "1001",
        "series_id": 8048,
        "meta": {"matchInfo": {"venue": "Wankhede Stadium", "date": "2024-01-01"}},
        "comments": [
            {
                "inningNumber": 1,
                "overNumber": 0,
                "ballNumber": 1,
                "batsmanName": "Rohit Sharma",
                "bowlerName": "Trent Boult",
                "text": "Good length delivery outside off, defends solidly, no run",
                "totalRuns": 0,
                "isWicket": False,
            },
            {
                "inningNumber": 1,
                "overNumber": 0,
                "ballNumber": 2,
                "batsmanName": "Rohit Sharma",
                "bowlerName": "Trent Boult",
                "text": "Fuller delivery outside off stump, drives hard through covers for four",
                "totalRuns": 4,
                "isWicket": False,
            },
        ],
    }
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    (input_dir / "1001.json").write_text(json.dumps(match_json), encoding="utf-8")

    rows = parse_match_file(input_dir / "1001.json")
    assert len(rows) == 2

    deliveries, matches = parse_matches_dir(input_dir)
    assert isinstance(deliveries, pd.DataFrame)
    assert len(deliveries) == 2
    assert len(matches) == 1
    assert matches.iloc[0]["match_id"] == "1001"
    assert matches.iloc[0]["delivery_count"] == 2


def test_parse_match_file_missing_comments_key_logs_and_returns_empty(tmp_path: Path):
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    (input_dir / "9999.json").write_text(json.dumps({"match_id": "9999"}), encoding="utf-8")

    rows = parse_match_file(input_dir / "9999.json")
    assert rows == []

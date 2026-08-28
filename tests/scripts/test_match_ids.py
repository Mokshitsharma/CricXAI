import json
from pathlib import Path

import requests

from scripts import match_ids


def test_load_manual_match_ids_missing_file_returns_empty(tmp_path: Path):
    result = match_ids.load_manual_match_ids(tmp_path / "does_not_exist.json")
    assert result == {}


def test_load_manual_match_ids_reads_and_stringifies_ids(tmp_path: Path):
    manual_file = tmp_path / "manual.json"
    manual_file.write_text(json.dumps({"world_cup_2023": [12345, "67890"]}), encoding="utf-8")

    result = match_ids.load_manual_match_ids(manual_file)
    assert result == {"world_cup_2023": ["12345", "67890"]}


def test_ensure_manual_file_scaffold_creates_all_tournament_keys(tmp_path: Path):
    manual_file = tmp_path / "manual.json"
    path = match_ids.ensure_manual_file_scaffold(manual_file)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data.keys()) == set(match_ids.TOURNAMENTS.keys())
    assert all(value == [] for value in data.values())


def test_extract_match_ids_from_nested_content_shape():
    data = {"content": {"matches": [{"objectId": 111}, {"matchId": 222}, {"id": "333"}]}}
    assert match_ids._extract_match_ids(data) == ["111", "222", "333"]


def test_extract_match_ids_handles_unexpected_shape():
    assert match_ids._extract_match_ids({"unexpected": "shape"}) == []
    assert match_ids._extract_match_ids([]) == []


def test_resolve_match_ids_falls_back_to_manual_when_no_series_id(tmp_path: Path, monkeypatch):
    manual_file = tmp_path / "manual.json"
    manual_file.write_text(json.dumps({"world_cup_2023": ["1", "2"]}), encoding="utf-8")

    # world_cup_2023 has no configured series ID in TOURNAMENTS, so this
    # must resolve purely from the manual file without any network call.
    result = match_ids.resolve_match_ids(tournament="world_cup_2023", manual_file=manual_file)
    assert result == ["1", "2"]


def test_fetch_series_match_ids_returns_empty_on_request_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("no network")

    monkeypatch.setattr(match_ids.requests, "get", boom)
    result = match_ids.fetch_series_match_ids(series_id=8048)
    assert result == []

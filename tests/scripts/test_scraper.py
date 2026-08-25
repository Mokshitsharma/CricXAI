import json
from pathlib import Path

from scripts import scraper


def test_build_comments_url_shape():
    url = scraper.build_comments_url("12345", 8048, page=2)
    assert "eventId=12345" in url
    assert "leagueId=8048" in url
    assert "page=2" in url


def test_scrape_match_is_idempotent(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "raw"
    output_dir.mkdir()
    existing = output_dir / "12345.json"
    existing.write_text(json.dumps({"match_id": "12345", "comments": []}), encoding="utf-8")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not make a network request for an already-saved match")

    monkeypatch.setattr(scraper, "fetch_json_with_retries", fail_if_called)

    result = scraper.scrape_match("12345", series_id=8048, output_dir=output_dir)
    assert result is None


def test_scrape_match_saves_combined_comments(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "raw"

    pages = [
        {"comments": [{"text": "ball 1"}, {"text": "ball 2"}], "pagination": {"pageCount": 2}, "teams": ["A", "B"]},
        {"comments": [{"text": "ball 3"}], "pagination": {"pageCount": 2}},
    ]
    call_count = {"n": 0}

    def fake_fetch(session, url, logger, timeout=20, max_retries=3):
        data = pages[call_count["n"]]
        call_count["n"] += 1
        return data

    monkeypatch.setattr(scraper, "fetch_json_with_retries", fake_fetch)
    monkeypatch.setattr(scraper.time, "sleep", lambda seconds: None)

    result = scraper.scrape_match("999", series_id=8048, output_dir=output_dir)
    assert result is not None
    saved = json.loads(result.read_text(encoding="utf-8"))
    assert len(saved["comments"]) == 3
    assert saved["meta"]["teams"] == ["A", "B"]


def test_scrape_match_stops_when_no_pagination_and_empty_payload(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "raw"

    def fake_fetch(session, url, logger, timeout=20, max_retries=3):
        return {"comments": []}

    monkeypatch.setattr(scraper, "fetch_json_with_retries", fake_fetch)
    monkeypatch.setattr(scraper.time, "sleep", lambda seconds: None)

    result = scraper.scrape_match("888", series_id=8048, output_dir=output_dir)
    saved = json.loads(result.read_text(encoding="utf-8"))
    assert saved["comments"] == []

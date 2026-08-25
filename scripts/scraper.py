"""Scrape ESPNcricinfo ball-by-ball commentary for ODI matches.

Ported from an earlier standalone commentary fetcher's retry/backoff and
pagination handling, reshaped per this project's scraping contract:

- One combined JSON file per match under ``data/raw/{match_id}.json``
  (not one file per page) — this is what ``scripts/nlp_parser.py`` consumes.
- Idempotent: a match already saved on disk is never re-fetched.
- Polite by default: sleeps between every request, between matches, and
  takes a longer pause every few matches, so repeated scheduled runs (see
  the GitHub Actions workflow) don't hammer ESPN's unofficial API.

ESPNcricinfo does not publish this commentary endpoint as a stable public
API. If scraping starts failing, inspect the match page's network requests
and update ``BASE_COMMENTS_URL`` / ``build_comments_url`` here.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import requests

from app.utils.file_io import ensure_dir, write_json
from app.utils.logger import get_logger
from scripts.match_ids import TOURNAMENTS, resolve_match_ids


BASE_COMMENTS_URL = "https://hs-consumer-api.espncricinfo.com/v1/pages/match/comments"
DEFAULT_OUTPUT_DIR = Path("data/raw")
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RETRIES = 3
DEFAULT_BATCH_SIZE = 15

REQUEST_SLEEP_SECONDS = 2.5
MATCH_SLEEP_SECONDS = 5.0
MATCHES_PER_PAUSE = 5
BATCH_PAUSE_SECONDS = 15.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CricXAI/0.1; +https://github.com/cricxai/cricxai)"
    ),
    "Accept": "application/json,text/plain,*/*",
}


class ScrapeError(RuntimeError):
    """Raised when a match's commentary cannot be fetched after retries."""


def build_comments_url(match_id: str, series_id: int, page: int, language: str = "en") -> str:
    """Build the ESPNcricinfo commentary endpoint URL for one page."""
    return (
        f"{BASE_COMMENTS_URL}"
        f"?lang={language}"
        f"&leagueId={series_id}"
        f"&eventId={match_id}"
        f"&liveTest=false"
        f"&filter=full"
        f"&page={page}"
    )


def fetch_json_with_retries(
    session: requests.Session,
    url: str,
    logger,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Fetch JSON with retry and exponential backoff."""
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Requesting %s (attempt %s/%s)", url, attempt, max_retries)
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.JSONDecodeError as exc:
            last_error = exc
            logger.warning("Response was not valid JSON: %s", exc)
        except requests.exceptions.RequestException as exc:
            last_error = exc
            logger.warning("Request failed: %s", exc)

        if attempt < max_retries:
            sleep_for = 2 ** (attempt - 1)
            logger.info("Retrying after %s second(s)", sleep_for)
            time.sleep(sleep_for)

    raise ScrapeError(
        "Unable to fetch ESPNcricinfo commentary JSON after retries. "
        "The endpoint structure may have changed and may need updating."
    ) from last_error


def get_page_count(data: dict[str, Any]) -> int | None:
    """Return total page count when the response includes pagination metadata."""
    pagination = data.get("pagination")
    if not isinstance(pagination, dict):
        return None
    page_count = pagination.get("pageCount")
    if isinstance(page_count, int):
        return page_count
    try:
        return int(page_count)
    except (TypeError, ValueError):
        return None


def has_commentary_payload(data: dict[str, Any]) -> bool:
    """Return whether a response appears to contain commentary records."""
    comments = data.get("comments")
    return isinstance(comments, list) and len(comments) > 0


def match_output_path(match_id: str, output_dir: Path) -> Path:
    """Path a single combined match JSON file is saved to."""
    return output_dir / f"{match_id}.json"


def scrape_match(
    match_id: str,
    series_id: int,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    request_sleep_seconds: float = REQUEST_SLEEP_SECONDS,
    session: requests.Session | None = None,
    logger=None,
) -> Path | None:
    """Scrape and save one match's full commentary as a single JSON file.

    Returns ``None`` without making any request if the match is already
    saved on disk (idempotent scraping).
    """
    logger = logger or get_logger(__name__)
    output_path = match_output_path(match_id, output_dir)

    if output_path.exists():
        logger.info("Skipping match %s: already saved at %s", match_id, output_path)
        return None

    session = session or requests.Session()
    session.headers.update(HEADERS)

    all_comments: list[Any] = []
    meta: dict[str, Any] = {}
    page = 1
    page_count: int | None = None

    while True:
        url = build_comments_url(match_id, series_id, page)
        data = fetch_json_with_retries(session, url, logger, timeout=timeout, max_retries=max_retries)

        if page == 1:
            # Preserve whatever match-level fields (teams, venue, date, etc.)
            # the API returns alongside "comments" and "pagination" on the
            # first page. Exact field names are unofficial/undocumented;
            # parse_espn_commentary and parse_matches downstream handle
            # missing fields defensively.
            meta = {key: value for key, value in data.items() if key not in ("comments", "pagination")}

        comments = data.get("comments")
        if isinstance(comments, list):
            all_comments.extend(comments)

        if page_count is None:
            page_count = get_page_count(data)

        if page_count is not None and page >= page_count:
            break
        if page_count is None and not has_commentary_payload(data):
            break

        page += 1
        time.sleep(request_sleep_seconds)

    match_record = {
        "match_id": match_id,
        "series_id": series_id,
        "pages_fetched": page if all_comments else 0,
        "meta": meta,
        "comments": all_comments,
    }

    ensure_dir(output_dir)
    write_json(match_record, output_path)
    logger.info("Saved match %s (%s commentary records) to %s", match_id, len(all_comments), output_path)
    return output_path


def scrape_batch(
    tournament: str | None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    manual_file: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    logger=None,
) -> list[Path]:
    """Scrape up to ``batch_size`` not-yet-saved matches.

    Iterates tournaments in ``scripts.match_ids.TOURNAMENTS`` order (or just
    the one requested), resolving match IDs per tournament and skipping any
    tournament with no configured series ID (can't build a commentary URL
    without one, even if manual match IDs exist for it).
    """
    logger = logger or get_logger(__name__)
    resolve_kwargs = {"manual_file": manual_file} if manual_file else {}

    tournaments = [tournament] if tournament else list(TOURNAMENTS.keys())
    saved_paths: list[Path] = []
    session = requests.Session()
    session.headers.update(HEADERS)
    matches_attempted = 0

    for name in tournaments:
        series_id = TOURNAMENTS.get(name)
        if series_id is None:
            logger.warning(
                "Skipping tournament '%s': no series ID configured in "
                "scripts.match_ids.TOURNAMENTS yet.",
                name,
            )
            continue

        match_ids = resolve_match_ids(tournament=name, logger=logger, **resolve_kwargs)
        pending_match_ids = [
            match_id for match_id in match_ids if not match_output_path(match_id, output_dir).exists()
        ]

        for match_id in pending_match_ids:
            if len(saved_paths) >= batch_size:
                logger.info("Batch size %s reached; stopping.", batch_size)
                return saved_paths

            try:
                saved_path = scrape_match(
                    match_id=match_id,
                    series_id=series_id,
                    output_dir=output_dir,
                    timeout=timeout,
                    max_retries=max_retries,
                    session=session,
                    logger=logger,
                )
            except ScrapeError as exc:
                logger.error("Failed to scrape match %s: %s", match_id, exc)
                continue

            if saved_path is None:
                continue

            saved_paths.append(saved_path)
            matches_attempted += 1

            if matches_attempted % MATCHES_PER_PAUSE == 0:
                logger.info("Pausing %.0f second(s) after %s matches", BATCH_PAUSE_SECONDS, matches_attempted)
                time.sleep(BATCH_PAUSE_SECONDS)
            else:
                time.sleep(MATCH_SLEEP_SECONDS)

    return saved_paths


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Scrape ESPNcricinfo ODI commentary in small batches.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Maximum number of new matches to scrape this run.",
    )
    parser.add_argument(
        "--tournament",
        choices=sorted(TOURNAMENTS.keys()),
        help="Limit scraping to one known tournament. Default: all tournaments.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory match JSON files are saved under.",
    )
    parser.add_argument(
        "--manual-file",
        type=Path,
        help="Path to the hand-curated match-id JSON file (see scripts.match_ids).",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_MAX_RETRIES)
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    logger = get_logger(__name__)

    saved_paths = scrape_batch(
        tournament=args.tournament,
        batch_size=args.batch_size,
        output_dir=args.output_dir,
        manual_file=args.manual_file,
        timeout=args.timeout,
        max_retries=args.retries,
        logger=logger,
    )

    logger.info("Finished. Scraped %s new match(es).", len(saved_paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

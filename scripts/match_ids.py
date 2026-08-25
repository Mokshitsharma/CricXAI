"""Resolve ODI match IDs to scrape.

ESPNcricinfo does not publish a stable, documented "list every ODI match"
endpoint. This module tries a best-effort series-schedule API call per known
tournament, and falls back to a manually curated JSON file
(``data/match_ids_manual.json``) that the user can hand-edit whenever the API
shape changes or a tournament needs match IDs added by hand. This mirrors
the same "unofficial API, verify and adjust" caution used for the commentary
endpoint elsewhere in this project.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests

from app.utils.file_io import ensure_dir, read_json, write_json
from app.utils.logger import get_logger


SERIES_SCHEDULE_URL = "https://hs-consumer-api.espncricinfo.com/v1/pages/series/schedule"
DEFAULT_TIMEOUT_SECONDS = 20

DEFAULT_MANUAL_FILE = Path("data/match_ids_manual.json")

# Known ODI tournaments this project targets, mapped to their ESPNcricinfo
# series IDs. Series IDs are looked up manually from the series URL on
# espncricinfo.com (e.g. espncricinfo.com/series/{slug}-{series_id}/...).
# Fill in real IDs as tournaments are added; a placeholder of ``None`` means
# "not yet resolved, use the manual match-id file instead."
TOURNAMENTS: dict[str, int | None] = {
    "world_cup_2023": None,
    "bilateral_2024": None,
    "champions_trophy_2025": None,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CricXAI/0.1; +https://github.com/cricxai/cricxai)"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def fetch_series_match_ids(
    series_id: int,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    logger=None,
) -> list[str]:
    """Fetch match IDs for one series from ESPNcricinfo's schedule API.

    Returns an empty list (and logs a warning) if the response doesn't have
    the shape this function expects — callers should fall back to the
    manual match-id file rather than treating that as a hard failure, since
    the endpoint is unofficial and may change without notice.
    """
    logger = logger or get_logger(__name__)
    url = f"{SERIES_SCHEDULE_URL}?lang=en&seriesId={series_id}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        logger.warning("Series schedule request failed for series %s: %s", series_id, exc)
        return []
    except ValueError as exc:
        logger.warning("Series schedule response was not valid JSON for series %s: %s", series_id, exc)
        return []

    match_ids = _extract_match_ids(data)
    if not match_ids:
        logger.warning(
            "No match IDs found in series %s schedule response. The endpoint "
            "shape may have changed; use the manual match-id file instead.",
            series_id,
        )
    return match_ids


def _extract_match_ids(data: Any) -> list[str]:
    """Best-effort extraction of match IDs from a schedule API response."""
    match_ids: list[str] = []

    content = data.get("content") if isinstance(data, dict) else None
    matches = content.get("matches") if isinstance(content, dict) else None
    if not isinstance(matches, list):
        matches = data.get("matches") if isinstance(data, dict) else None

    if not isinstance(matches, list):
        return match_ids

    for match in matches:
        if not isinstance(match, dict):
            continue
        match_id = match.get("objectId") or match.get("matchId") or match.get("id")
        if match_id is not None:
            match_ids.append(str(match_id))

    return match_ids


def load_manual_match_ids(manual_file: Path = DEFAULT_MANUAL_FILE) -> dict[str, list[str]]:
    """Load the hand-curated tournament -> match-id list mapping.

    Returns an empty mapping (not an error) if the file doesn't exist yet,
    since a fresh checkout won't have one until someone creates it.
    """
    if not manual_file.exists():
        return {}
    data = read_json(manual_file)
    if not isinstance(data, dict):
        return {}
    return {
        tournament: [str(match_id) for match_id in match_ids]
        for tournament, match_ids in data.items()
        if isinstance(match_ids, list)
    }


def ensure_manual_file_scaffold(manual_file: Path = DEFAULT_MANUAL_FILE) -> Path:
    """Create an empty manual match-id file scaffold if none exists yet."""
    if manual_file.exists():
        return manual_file
    ensure_dir(manual_file.parent)
    return write_json({tournament: [] for tournament in TOURNAMENTS}, manual_file)


def resolve_match_ids(
    tournament: str | None = None,
    manual_file: Path = DEFAULT_MANUAL_FILE,
    logger=None,
) -> list[str]:
    """Resolve match IDs to scrape: try the API first, fall back to manual.

    When ``tournament`` is None, resolves match IDs across every known
    tournament.
    """
    logger = logger or get_logger(__name__)
    manual_ids = load_manual_match_ids(manual_file)

    tournaments = [tournament] if tournament else list(TOURNAMENTS.keys())
    resolved: list[str] = []

    for name in tournaments:
        series_id = TOURNAMENTS.get(name)
        api_ids: list[str] = []
        if series_id is not None:
            api_ids = fetch_series_match_ids(series_id, logger=logger)

        ids_for_tournament = api_ids or manual_ids.get(name, [])
        if not ids_for_tournament:
            logger.warning(
                "No match IDs resolved for tournament '%s' (no series ID configured "
                "or manual entries found). Add IDs to %s.",
                name,
                manual_file,
            )
        resolved.extend(ids_for_tournament)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduplicated: list[str] = []
    for match_id in resolved:
        if match_id not in seen:
            seen.add(match_id)
            deduplicated.append(match_id)
    return deduplicated


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Resolve ODI match IDs to scrape.")
    parser.add_argument(
        "--tournament",
        choices=sorted(TOURNAMENTS.keys()),
        help="Limit resolution to one known tournament. Default: all tournaments.",
    )
    parser.add_argument(
        "--manual-file",
        type=Path,
        default=DEFAULT_MANUAL_FILE,
        help="Path to the hand-curated match-id JSON file.",
    )
    parser.add_argument(
        "--init-manual-file",
        action="store_true",
        help="Create an empty manual match-id file scaffold and exit.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    logger = get_logger(__name__)

    if args.init_manual_file:
        path = ensure_manual_file_scaffold(args.manual_file)
        logger.info("Manual match-id file scaffold ready at %s", path)
        return 0

    match_ids = resolve_match_ids(
        tournament=args.tournament,
        manual_file=args.manual_file,
        logger=logger,
    )
    logger.info("Resolved %s match ID(s)", len(match_ids))
    for match_id in match_ids:
        print(match_id)
    return 0 if match_ids else 1


if __name__ == "__main__":
    raise SystemExit(main())

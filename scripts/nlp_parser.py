"""Turn raw ESPNcricinfo commentary text into structured ball-by-ball data.

Raw match JSON (saved by ``scripts/scraper.py`` as ``data/raw/{match_id}.json``)
holds a list of commentary records whose exact field names are unofficial
and undocumented. This module extracts what it can defensively (multiple
candidate field names, never a hard failure on a missing field) and, for the
cricket-specific signals that only exist as free text (ball length, ball
line, shot type), uses fixed phrase-matching dictionaries scanned in a
deliberate precedence order so overlapping phrases resolve deterministically
(e.g. "wide outside off stump" must match ``wide_outside_off`` before the
more general ``outside_off`` gets a chance).

Outputs two tables:
- ``deliveries.csv``: one row per ball.
- ``matches.csv``: one row per match (best-effort metadata).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from app.utils.cricket_constants import (
    BALL_LENGTHS,
    BALL_LINES,
    DISMISSAL_TYPES,
    SHOT_TYPES,
)
from app.utils.file_io import ensure_dir, list_files, read_json
from app.utils.logger import get_logger


DEFAULT_INPUT_DIR = Path("data/raw")
DEFAULT_OUTPUT_DIR = Path("data/processed")
UNKNOWN = "unknown"

# ---------------------------------------------------------------------------
# Phrase dictionaries. Order matters: more specific categories are listed
# before the general categories they could be confused with.
# ---------------------------------------------------------------------------

LENGTH_PHRASES: dict[str, tuple[str, ...]] = {
    "yorker": ("yorker", "toe crushing", "toe-crushing", "at the base of the stumps", "full length, right on the blockhole"),
    "bouncer": ("bouncer", "short and rising", "bounced it", "climbing delivery", "chin music", "short-pitched, rearing up"),
    "full": ("full delivery", "fuller delivery", "fuller length", "fuller", "full toss", "pitched up", "overpitched", "full and straight"),
    "short": ("short of a length", "short ball", "short pitched", "short-pitched", "back of a length", "sat up", "short delivery"),
    "good": ("good length", "on a length", "hits the deck", "back of good length"),
}

LINE_PHRASES: dict[str, tuple[str, ...]] = {
    "wide_outside_off": ("wide outside off", "wide of off stump", "well outside off"),
    "wide_down_leg": ("down the leg side, well wide", "wide down leg", "well down the leg side"),
    "outside_off": ("outside off stump", "outside the off stump", "channel outside off", "corridor of uncertainty"),
    "down_leg": ("down leg", "down the leg side", "on the pads", "leg side delivery"),
    "off_stump": ("on off stump", "line of off stump", "just outside off"),
    "leg_stump": ("on leg stump", "line of leg stump", "into the pads"),
    "middle_stump": ("on middle stump", "straight delivery", "line of middle and leg", "on the stumps"),
}

SHOT_PHRASES: dict[str, tuple[str, ...]] = {
    "reverse_sweep": ("reverse sweep", "reverse-swept"),
    "sweep": ("sweeps", "swept", "sweep shot"),
    "cover_drive": ("drives", "driven", "through covers", "cover drive", "drills it through cover"),
    "straight_drive": ("straight drive", "driven straight", "back past the bowler"),
    "cut": ("cuts", "square cut", "late cut", "cut shot"),
    "pull": ("pulls", "pulled", "pull shot"),
    "hook": ("hooks", "hooked", "hook shot"),
    "flick": ("flicks", "flicked off the pads", "clipped off the pads"),
    "glance": ("glances", "glanced fine", "tickled"),
    "loft": ("lofts", "lofted", "hits it in the air", "goes over the top"),
    "defend": ("defends", "blocks", "defended solidly", "plays it back"),
    "leave": ("leaves it", "shoulders arms", "let it go"),
    "edge": ("edges", "outside edge", "inside edge", "thick edge", "thin edge"),
}

OUTCOME_PHRASES: dict[str, tuple[str, ...]] = {
    "leg_bye": ("leg bye", "leg byes"),
    "bye": ("bye", "byes"),
    "no_ball": ("no ball", "no-ball", "front foot no ball"),
    "wide": ("wide",),
    "six": ("six", "maximum", "into the stands"),
    "four": ("four runs", "boundary", "races away to the fence", "four!"),
    "dot": ("no run", "dot ball", "defended, no run"),
}

DISMISSAL_PHRASES: dict[str, tuple[str, ...]] = {
    "run_out": ("run out", "run-out", "direct hit"),
    "stumped": ("stumped", "stumping"),
    "hit_wicket": ("hit wicket", "hit-wicket", "dislodges the bail"),
    "lbw": ("lbw", "leg before wicket", "trapped in front"),
    "caught": ("caught", "holds on", "taken at", "catches it", "comfortably taken"),
    "bowled": ("bowled", "clean bowled", "castled", "knocks back the stumps", "knocks over the stumps"),
}
# Deliberately excludes short scorecard-shorthand tokens like "c " / "b " —
# those are too ambiguous as free-text substrings (e.g. "basic delivery").
# extract_dismissal() only ever calls this on balls already flagged as
# wickets by the API, and prefers the full commentary sentence over the
# terse dismissal_text field for exactly this reason.

assert set(LENGTH_PHRASES) <= set(BALL_LENGTHS)
assert set(LINE_PHRASES) <= set(BALL_LINES)
assert set(SHOT_PHRASES) <= set(SHOT_TYPES)
assert set(DISMISSAL_PHRASES) <= set(DISMISSAL_TYPES)


def _match_category(text: str, phrase_map: dict[str, tuple[str, ...]]) -> str | None:
    """Return the first matching category in a phrase map's declared order."""
    lowered = text.lower()
    for category, phrases in phrase_map.items():
        for phrase in phrases:
            if phrase in lowered:
                return category
    return None


def _get_first(record: dict[str, Any], *keys: str) -> Any:
    """Return the first present, non-None value among candidate top-level keys."""
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def _get_nested_name(record: dict[str, Any], *keys: str) -> str | None:
    """Return a name from either a flat string field or a nested {"name": ...} object."""
    value = _get_first(record, *keys)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        name = value.get("name") or value.get("fullName") or value.get("longName")
        if isinstance(name, str):
            return name
    return None


def _get_commentary_text(record: dict[str, Any]) -> str:
    """Return the commentary text for one delivery, joining item lists if needed."""
    text = _get_first(record, "text", "commentary", "commentaryText", "shortText")
    if isinstance(text, str):
        return text

    items = record.get("commentTextItems")
    if isinstance(items, list):
        pieces = [item.get("text", "") for item in items if isinstance(item, dict)]
        return " ".join(piece for piece in pieces if piece)

    return ""


def _get_over_and_ball(record: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (over, ball_in_over) from whichever fields the API provided."""
    over = _get_first(record, "overNumber", "over")
    ball = _get_first(record, "ballNumber", "ball")
    if over is not None and ball is not None:
        try:
            return int(over), int(ball)
        except (TypeError, ValueError):
            pass

    overs_string = _get_first(record, "oversUnique", "oversActual", "overs")
    if isinstance(overs_string, str) and "." in overs_string:
        whole, _, fraction = overs_string.partition(".")
        try:
            return int(whole), int(fraction)
        except ValueError:
            pass

    return None, None


def _get_total_runs(record: dict[str, Any]) -> int | None:
    value = _get_first(record, "totalRuns", "runs", "scoreValue")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _get_is_wicket(record: dict[str, Any]) -> bool:
    value = _get_first(record, "isWicket", "wicket")
    return bool(value)


def extract_outcome(text: str, total_runs: int | None, is_wicket: bool) -> str:
    """Determine what happened on the ball, preferring reliable numeric fields."""
    if is_wicket:
        return "wicket"
    if total_runs is not None:
        run_labels = {0: "dot", 1: "single", 2: "two", 3: "three", 4: "four", 6: "six"}
        if total_runs in run_labels:
            return run_labels[total_runs]
    phrase_outcome = _match_category(text, OUTCOME_PHRASES)
    return phrase_outcome or UNKNOWN


def extract_dismissal(text: str, dismissal_text: str | None, is_wicket: bool) -> str | None:
    """Determine dismissal type; returns None when the ball wasn't a wicket.

    Prefers the full commentary sentence (descriptive prose, e.g. "caught
    behind off a thick edge") over the terser ``dismissal_text`` field
    (often scorecard shorthand like "c Smith b Jones") since the phrase
    dictionary is tuned for descriptive language.
    """
    if not is_wicket:
        return None

    category = _match_category(text, DISMISSAL_PHRASES)
    if category:
        return category
    if isinstance(dismissal_text, str) and dismissal_text:
        category = _match_category(dismissal_text, DISMISSAL_PHRASES)
        if category:
            return category
    return UNKNOWN


def extract_signals(text: str) -> dict[str, str]:
    """Extract the free-text cricket signals from one delivery's commentary."""
    return {
        "ball_length": _match_category(text, LENGTH_PHRASES) or UNKNOWN,
        "ball_line": _match_category(text, LINE_PHRASES) or UNKNOWN,
        "shot_type": _match_category(text, SHOT_PHRASES) or UNKNOWN,
    }


def parse_delivery(record: dict[str, Any], match_id: str) -> dict[str, Any] | None:
    """Parse one raw commentary record into a structured delivery row."""
    if not isinstance(record, dict):
        return None

    text = _get_commentary_text(record)
    over, ball_in_over = _get_over_and_ball(record)
    total_runs = _get_total_runs(record)
    is_wicket = _get_is_wicket(record)
    dismissal_text = _get_first(record, "dismissalText", "dismissal", "wicketText")

    signals = extract_signals(text)

    return {
        "match_id": match_id,
        "innings": _get_first(record, "inningNumber", "inningsId", "innings") or 1,
        "over": over,
        "ball_in_over": ball_in_over,
        "batsman": _get_nested_name(record, "batsmanName", "batsman", "batter"),
        "bowler": _get_nested_name(record, "bowlerName", "bowler"),
        "text": text,
        "total_runs": total_runs,
        "ball_length": signals["ball_length"],
        "ball_line": signals["ball_line"],
        "shot_type": signals["shot_type"],
        "outcome": extract_outcome(text, total_runs, is_wicket),
        "is_wicket": is_wicket,
        "dismissal_type": extract_dismissal(text, dismissal_text, is_wicket),
        "player_out": _get_nested_name(record, "playerOut", "wicketPlayerName") if is_wicket else None,
    }


def parse_match_file(path: Path, logger=None) -> list[dict[str, Any]]:
    """Parse one raw match JSON file into a list of delivery rows."""
    logger = logger or get_logger(__name__)
    raw = read_json(path)

    match_id = str(raw.get("match_id", path.stem))
    comments = raw.get("comments")
    if not isinstance(comments, list):
        logger.warning("Match %s has no 'comments' list; skipping.", match_id)
        return []

    rows = [row for row in (parse_delivery(record, match_id) for record in comments) if row is not None]
    logger.info("Parsed %s delivery record(s) from match %s", len(rows), match_id)
    return rows


def parse_match_metadata(path: Path) -> dict[str, Any]:
    """Best-effort extraction of one match's metadata row."""
    raw = read_json(path)
    match_id = str(raw.get("match_id", path.stem))
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}

    match_info = meta.get("matchInfo") if isinstance(meta.get("matchInfo"), dict) else meta

    return {
        "match_id": match_id,
        "series_id": raw.get("series_id"),
        "teams": _get_first(match_info, "teams", "competitors"),
        "venue": _get_nested_name(match_info, "venue", "ground") or match_info.get("venue"),
        "date": _get_first(match_info, "date", "startDate", "matchDate"),
        "result": _get_first(match_info, "result", "statusText", "outcome"),
        "delivery_count": None,  # filled in by parse_matches_dir once deliveries are known
    }


def log_extraction_quality(deliveries: pd.DataFrame, logger) -> None:
    """Log the percentage of rows where each extracted field was resolved."""
    if deliveries.empty:
        return
    for column in ("ball_length", "ball_line", "shot_type"):
        matched = (deliveries[column] != UNKNOWN).mean() * 100
        logger.info("Extraction quality for '%s': %.1f%% matched", column, matched)

    wickets = deliveries[deliveries["is_wicket"]]
    if not wickets.empty:
        matched = (wickets["dismissal_type"] != UNKNOWN).mean() * 100
        logger.info("Extraction quality for 'dismissal_type': %.1f%% matched (of %s wickets)", matched, len(wickets))


def parse_matches_dir(input_dir: Path, logger=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse every raw match JSON file in a directory into two DataFrames."""
    logger = logger or get_logger(__name__)
    match_files = list_files(input_dir, "*.json")

    all_rows: list[dict[str, Any]] = []
    match_metadata: list[dict[str, Any]] = []

    for match_file in match_files:
        rows = parse_match_file(match_file, logger=logger)
        all_rows.extend(rows)

        metadata = parse_match_metadata(match_file)
        metadata["delivery_count"] = len(rows)
        match_metadata.append(metadata)

    deliveries = pd.DataFrame(all_rows)
    matches = pd.DataFrame(match_metadata)

    log_extraction_quality(deliveries, logger)
    return deliveries, matches


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Parse raw ESPN commentary into structured deliveries.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    logger = get_logger(__name__)

    deliveries, matches = parse_matches_dir(args.input_dir, logger=logger)
    if deliveries.empty:
        logger.warning("No deliveries parsed from %s", args.input_dir)
        return 1

    ensure_dir(args.output_dir)
    deliveries_path = args.output_dir / "deliveries.csv"
    matches_path = args.output_dir / "matches.csv"
    deliveries.to_csv(deliveries_path, index=False)
    matches.to_csv(matches_path, index=False)

    logger.info("Wrote %s delivery row(s) to %s", len(deliveries), deliveries_path)
    logger.info("Wrote %s match row(s) to %s", len(matches), matches_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

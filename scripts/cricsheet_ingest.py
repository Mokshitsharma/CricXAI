"""Ingest Cricsheet ODI JSON into CricXAI's ball-by-ball tables.

Cricsheet (https://cricsheet.org, ODC-BY) publishes one JSON file per match
at scorecard + outcome granularity. It has **no ball length / line / shot
type / speed** — those columns are emitted as ``"unknown"`` and the
length x line recommendation layer cannot be trained from this source
(see ``data/external/cricsheet/SOURCE.md`` and ``docs/PHASES.md``).

What this script *does* give the models is ~1.3M real deliveries of match
context, real batsman dismissal profiles and real dismissal-type mix, in
exactly the schema ``scripts/nlp_parser.py`` produces, so
``scripts/build_features.py`` and ``scripts/train.py`` consume the output
unchanged. Every row is tagged ``source="cricsheet"``.

Usage::

    python -m scripts.cricsheet_ingest                       # men's ODIs
    python -m scripts.cricsheet_ingest --gender female
    python -m scripts.cricsheet_ingest --since 2015-01-01 --top-nations-only
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from app.utils.file_io import ensure_dir
from app.utils.logger import get_logger

DEFAULT_ARCHIVE = Path("data/external/cricsheet/odis_json.zip")
DEFAULT_OUTPUT_DIR = Path("data/processed")
UNKNOWN = "unknown"
SOURCE = "cricsheet"

# CricXAI's ten target nations (docs/PRD.md). Afghanistan is listed for
# completeness but Cricsheet withholds all Afghanistan men's matches.
TOP_NATIONS = {
    "India", "Australia", "England", "South Africa", "New Zealand",
    "Pakistan", "Sri Lanka", "Bangladesh", "Afghanistan", "West Indies",
}

# Cricsheet wicket "kind" -> CricXAI DISMISSAL_TYPES (None => not a batter
# dismissal we model; the ball is still recorded, just not is_wicket).
_WICKET_KIND_MAP: dict[str, str | None] = {
    "caught": "caught",
    "bowled": "bowled",
    "lbw": "lbw",
    "run out": "run_out",
    "stumped": "stumped",
    "hit wicket": "hit_wicket",
    "caught and bowled": "caught",
    "obstructing the field": None,
    "handled the ball": None,
    "hit the ball twice": None,
    "timed out": None,
    "retired hurt": None,
    "retired out": None,
    "retired not out": None,
}
# Kinds that still count as a wicket falling (dismissal_type left UNKNOWN,
# so M2 skips them but M1 sees the positive). Retirements never count.
_WICKET_NONMODELLED = {
    "obstructing the field", "handled the ball", "hit the ball twice", "timed out",
}

_RUN_LABELS = {0: "dot", 1: "single", 2: "two", 3: "three", 4: "four", 5: "four", 6: "six"}


def _outcome_and_wicket(delivery: dict[str, Any]) -> tuple[str, bool, str | None, str | None]:
    """Return (outcome, is_wicket, dismissal_type, player_out) for one delivery."""
    wickets = delivery.get("wickets") or []
    for w in wickets:
        kind = str(w.get("kind", "")).lower()
        mapped = _WICKET_KIND_MAP.get(kind)
        if mapped is not None:
            return "wicket", True, mapped, w.get("player_out")
        if kind in _WICKET_NONMODELLED:
            return "wicket", True, UNKNOWN, w.get("player_out")
        # retirement: fall through, not a modelled wicket

    extras = delivery.get("extras") or {}
    if "wides" in extras:
        return "wide", False, None, None
    if "noballs" in extras:
        return "no_ball", False, None, None

    runs_total = int((delivery.get("runs") or {}).get("total", 0))
    return _RUN_LABELS.get(runs_total, "six"), False, None, None


def parse_match(raw: dict[str, Any], match_id: str) -> tuple[list[dict], dict | None]:
    """Parse one Cricsheet match dict into (delivery_rows, match_meta)."""
    info = raw.get("info", {})
    teams = info.get("teams", [])
    if len(teams) != 2:
        return [], None

    rows: list[dict] = []
    innings_runs: dict[int, int] = {}

    for innings_idx, innings in enumerate(raw.get("innings", []), start=1):
        if innings_idx > 2:  # super overs — out of scope for the 50-over models
            break
        batting_team = innings.get("team")
        total = 0
        for over_obj in innings.get("overs", []):
            over_no = int(over_obj.get("over", 0))
            for ball_pos, delivery in enumerate(over_obj.get("deliveries", []), start=1):
                runs_total = int((delivery.get("runs") or {}).get("total", 0))
                total += runs_total
                outcome, is_wicket, dismissal_type, player_out = _outcome_and_wicket(delivery)
                rows.append(
                    {
                        "match_id": match_id,
                        "innings": innings_idx,
                        "over": over_no,
                        "ball_in_over": ball_pos,
                        "batsman": delivery.get("batter"),
                        "bowler": delivery.get("bowler"),
                        "text": "",
                        "total_runs": runs_total,
                        "ball_length": UNKNOWN,
                        "ball_line": UNKNOWN,
                        "shot_type": UNKNOWN,
                        "outcome": outcome,
                        "is_wicket": is_wicket,
                        "dismissal_type": dismissal_type,
                        "player_out": player_out,
                        "batting_team": batting_team,
                        "source": SOURCE,
                    }
                )
        innings_runs[innings_idx] = total

    if not rows:
        return [], None

    event = info.get("event") or {}
    meta = {
        "match_id": match_id,
        "series_id": event.get("name") or "CRICSHEET",
        "source": SOURCE,
        "teams": f"{teams[0]} vs {teams[1]}",
        "home_team": teams[0],
        "away_team": teams[1],
        "venue": info.get("venue"),
        "date": (info.get("dates") or [None])[0],
        "result": _format_result(info.get("outcome") or {}),
        "innings1_runs": innings_runs.get(1, 0),
        "innings2_runs": innings_runs.get(2, 0),
        "delivery_count": len(rows),
    }
    return rows, meta


def _format_result(outcome: dict[str, Any]) -> str:
    if outcome.get("result") == "tie":
        return "Match tied"
    if outcome.get("result") in ("no result", "draw"):
        return str(outcome["result"]).title()
    winner = outcome.get("winner")
    by = outcome.get("by") or {}
    if winner and "runs" in by:
        return f"{winner} won by {by['runs']} runs"
    if winner and "wickets" in by:
        return f"{winner} won by {by['wickets']} wickets"
    return str(outcome.get("result") or "unknown")


def _keep_match(info: dict[str, Any], gender: str, since: str | None, top_only: bool) -> bool:
    if info.get("match_type") != "ODI":
        return False
    if info.get("gender") != gender:
        return False
    if info.get("balls_per_over") not in (6, None):
        return False
    if since:
        date = (info.get("dates") or [""])[0]
        if date and date < since:
            return False
    return not (top_only and not set(info.get("teams", [])).issubset(TOP_NATIONS))


def ingest_archive(
    archive: Path,
    gender: str = "male",
    since: str | None = None,
    top_only: bool = False,
    logger=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger = logger or get_logger(__name__)
    all_rows: list[dict] = []
    all_meta: list[dict] = []
    kept = skipped = 0

    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json")]
        logger.info("Archive %s: %s match files", archive, len(names))
        for name in names:
            with zf.open(name) as fh:
                raw = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
            if not _keep_match(raw.get("info", {}), gender, since, top_only):
                skipped += 1
                continue
            match_id = Path(name).stem
            rows, meta = parse_match(raw, match_id)
            if meta is None:
                skipped += 1
                continue
            all_rows.extend(rows)
            all_meta.append(meta)
            kept += 1
            if kept % 250 == 0:
                logger.info("  parsed %s matches (%s deliveries so far)", kept, len(all_rows))

    deliveries = pd.DataFrame(all_rows)
    matches = pd.DataFrame(all_meta)
    logger.info(
        "Ingested %s matches, %s deliveries, %s wickets (skipped %s files)",
        kept, len(deliveries), int(deliveries["is_wicket"].sum()) if not deliveries.empty else 0,
        skipped,
    )
    return deliveries, matches


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest Cricsheet ODI JSON into CricXAI tables.")
    p.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--gender", choices=["male", "female"], default="male")
    p.add_argument("--since", help="ISO date lower bound, e.g. 2015-01-01")
    p.add_argument("--top-nations-only", action="store_true",
                   help="keep only matches where both teams are CricXAI target nations")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logger = get_logger(__name__)
    if not args.archive.exists():
        logger.error("Archive not found: %s", args.archive)
        return 1

    deliveries, matches = ingest_archive(
        args.archive, gender=args.gender, since=args.since,
        top_only=args.top_nations_only, logger=logger,
    )
    if deliveries.empty:
        logger.error("No deliveries ingested — check filters.")
        return 1

    ensure_dir(args.output_dir)
    deliveries_path = args.output_dir / "deliveries.csv"
    matches_path = args.output_dir / "matches.csv"
    deliveries.to_csv(deliveries_path, index=False)
    matches.to_csv(matches_path, index=False)
    logger.info("Wrote %s and %s", deliveries_path, matches_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

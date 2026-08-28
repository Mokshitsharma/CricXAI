"""Reference vocabulary — the enums the console and API clients need."""

from __future__ import annotations

from fastapi import APIRouter

from app.utils.cricket_constants import (
    BALL_LENGTHS,
    BALL_LINES,
    BOWLER_TYPES,
    DISMISSAL_TYPES,
    PHASES,
    SHOT_TYPES,
)

router = APIRouter(tags=["reference"])


@router.get("/reference")
def reference() -> dict:
    return {
        "phases": list(PHASES),
        "ball_lengths": list(BALL_LENGTHS),
        "ball_lines": list(BALL_LINES),
        "bowler_types": list(BOWLER_TYPES),
        "dismissal_types": list(DISMISSAL_TYPES),
        "shot_types": list(SHOT_TYPES),
    }

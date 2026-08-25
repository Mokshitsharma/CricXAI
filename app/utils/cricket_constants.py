"""Shared cricket vocabulary and encodings.

Defined once here so the NLP parser (which extracts these categories from
commentary text) and the feature engineer / strategy engine (which encode
and consume them) never drift out of sync.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Match phase (ODI, 50 overs per innings)
# ---------------------------------------------------------------------------

PHASES: tuple[str, ...] = (
    "powerplay",
    "early_middle",
    "middle",
    "late_middle",
    "death",
)

PHASE_ENCODING: dict[str, int] = {phase: index for index, phase in enumerate(PHASES)}

UNKNOWN_ENCODING = -1


def phase_from_over(over_number: int) -> str:
    """Return the match phase for a zero-indexed ODI over number (0-49)."""
    if over_number < 10:
        return "powerplay"
    if over_number < 20:
        return "early_middle"
    if over_number < 30:
        return "middle"
    if over_number < 40:
        return "late_middle"
    return "death"


# ---------------------------------------------------------------------------
# Ball length
# ---------------------------------------------------------------------------

BALL_LENGTHS: tuple[str, ...] = (
    "yorker",
    "full",
    "good",
    "short",
    "bouncer",
)

BALL_LENGTH_ENCODING: dict[str, int] = {length: index for index, length in enumerate(BALL_LENGTHS)}

# ---------------------------------------------------------------------------
# Ball line
# ---------------------------------------------------------------------------

BALL_LINES: tuple[str, ...] = (
    "wide_outside_off",
    "outside_off",
    "off_stump",
    "middle_stump",
    "leg_stump",
    "down_leg",
    "wide_down_leg",
)

BALL_LINE_ENCODING: dict[str, int] = {line: index for index, line in enumerate(BALL_LINES)}

# ---------------------------------------------------------------------------
# Shot type
# ---------------------------------------------------------------------------

SHOT_TYPES: tuple[str, ...] = (
    "cover_drive",
    "straight_drive",
    "cut",
    "pull",
    "hook",
    "sweep",
    "reverse_sweep",
    "flick",
    "glance",
    "loft",
    "defend",
    "leave",
    "edge",
)

# ---------------------------------------------------------------------------
# Outcome (what happened on the ball, independent of dismissal)
# ---------------------------------------------------------------------------

OUTCOMES: tuple[str, ...] = (
    "dot",
    "single",
    "two",
    "three",
    "four",
    "six",
    "wide",
    "no_ball",
    "bye",
    "leg_bye",
    "wicket",
)

# ---------------------------------------------------------------------------
# Dismissal type
# ---------------------------------------------------------------------------

DISMISSAL_TYPES: tuple[str, ...] = (
    "caught",
    "bowled",
    "lbw",
    "run_out",
    "stumped",
    "hit_wicket",
)

DISMISSAL_TYPE_ENCODING: dict[str, int] = {
    dismissal: index for index, dismissal in enumerate(DISMISSAL_TYPES)
}

# ---------------------------------------------------------------------------
# Bowler type (used as strategy engine input, matches spec's phase input set)
# ---------------------------------------------------------------------------

BOWLER_TYPES: tuple[str, ...] = (
    "pace_right_arm",
    "pace_left_arm",
    "off_spin",
    "leg_spin",
    "left_arm_spin",
)

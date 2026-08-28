"""The candidate delivery grid the recommendation engine scores.

For a fixed bowler type, every plausible ``(length, line)`` pair. Physically
implausible pairs are dropped (a finger/wrist spinner does not bowl
bouncers; a genuine wide-down-leg is a mistake, not a plan).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.utils.cricket_constants import (
    BALL_LENGTH_ENCODING,
    BALL_LENGTHS,
    BALL_LINE_ENCODING,
    BALL_LINES,
)

SPIN_TYPES = {"off_spin", "leg_spin", "left_arm_spin"}
_SPIN_DROP_LENGTHS = {"bouncer"}
_ALWAYS_DROP_LINES = {"wide_down_leg"}


@dataclass(frozen=True)
class Candidate:
    length: str
    line: str
    length_encoded: int
    line_encoded: int

    @property
    def label(self) -> str:
        return f"{self.length.title()}, {self.line.replace('_', ' ')}"


def candidate_grid(bowler_type: str) -> list[Candidate]:
    is_spin = bowler_type in SPIN_TYPES
    grid: list[Candidate] = []
    for length in BALL_LENGTHS:
        if is_spin and length in _SPIN_DROP_LENGTHS:
            continue
        for line in BALL_LINES:
            if line in _ALWAYS_DROP_LINES:
                continue
            grid.append(
                Candidate(
                    length=length,
                    line=line,
                    length_encoded=BALL_LENGTH_ENCODING[length],
                    line_encoded=BALL_LINE_ENCODING[line],
                )
            )
    return grid

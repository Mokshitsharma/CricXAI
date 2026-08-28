"""Heuristic field selection (v1).

Maps ``(phase, length, line, bowler_type)`` to a named preset from
``field_presets``. A learned shot-direction model replaces this in Phase 4
(docs/PHASES.md).
"""

from __future__ import annotations

from app.engine.candidates import SPIN_TYPES
from app.engine.field_presets import FIELD_PRESETS


def choose_field(phase: str, length: str, line: str, bowler_type: str) -> dict:
    preset_key = _preset_key(phase, length, line, bowler_type)
    preset = FIELD_PRESETS[preset_key]
    return {
        "preset": preset_key,
        "label": preset["label"],
        "positions": [
            {"name": name, "x": x, "y": y} for (name, x, y) in preset["positions"]
        ],
    }


def _preset_key(phase: str, length: str, line: str, bowler_type: str) -> str:
    if length in ("short", "bouncer"):
        return "short_ball_trap"
    if bowler_type in SPIN_TYPES:
        return "spin_in_out"
    if phase == "death":
        return "death_yorker_ring"
    if phase == "powerplay":
        if line in ("outside_off", "off_stump", "wide_outside_off"):
            return "fourth_stump_catchers"
        return "powerplay_attack"
    if line in ("outside_off", "off_stump") and length in ("good", "full"):
        return "fourth_stump_catchers"
    return "middle_containment"

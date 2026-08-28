"""Named field presets: 9 fielding positions (keeper + bowler implied).

Positions are given as (x, y) on a normalised top-down half-field where the
striker is at (0.5, 0.9), the bowler runs in from (0.5, 0.05), x grows to the
off side for a right-hander, y grows toward the striker. The frontend mirrors
x for left-handers.
"""

from __future__ import annotations

POS = dict  # readability alias

FIELD_PRESETS: dict[str, dict] = {
    "powerplay_attack": {
        "label": "Powerplay attack",
        "positions": [
            ("slip", 0.66, 0.78), ("second_slip", 0.70, 0.76),
            ("gully", 0.76, 0.70), ("point", 0.85, 0.55),
            ("cover", 0.78, 0.40), ("mid_off", 0.58, 0.25),
            ("mid_on", 0.42, 0.25), ("mid_wicket", 0.28, 0.45),
            ("fine_leg", 0.30, 0.85),
        ],
    },
    "middle_containment": {
        "label": "Middle-overs containment",
        "positions": [
            ("slip", 0.66, 0.78), ("point", 0.86, 0.52),
            ("cover", 0.76, 0.40), ("mid_off", 0.58, 0.22),
            ("mid_on", 0.42, 0.22), ("mid_wicket", 0.24, 0.44),
            ("deep_mid_wicket", 0.16, 0.80), ("deep_square_leg", 0.14, 0.62),
            ("long_off", 0.56, 0.05),
        ],
    },
    "spin_in_out": {
        "label": "Spin in-out",
        "positions": [
            ("slip", 0.66, 0.78), ("silly_point", 0.62, 0.66),
            ("point", 0.86, 0.52), ("deep_cover", 0.82, 0.12),
            ("long_off", 0.56, 0.05), ("long_on", 0.44, 0.05),
            ("deep_mid_wicket", 0.16, 0.78), ("short_mid_wicket", 0.30, 0.46),
            ("deep_square_leg", 0.12, 0.60),
        ],
    },
    "death_yorker_ring": {
        "label": "Death yorker ring",
        "positions": [
            ("short_third", 0.78, 0.72), ("point", 0.86, 0.52),
            ("deep_cover", 0.84, 0.12), ("long_off", 0.56, 0.04),
            ("long_on", 0.44, 0.04), ("deep_mid_wicket", 0.16, 0.80),
            ("deep_square_leg", 0.12, 0.60), ("mid_off", 0.58, 0.24),
            ("mid_on", 0.42, 0.24),
        ],
    },
    "short_ball_trap": {
        "label": "Short-ball trap",
        "positions": [
            ("fine_leg_back", 0.30, 0.92), ("deep_square_leg", 0.12, 0.58),
            ("deep_mid_wicket", 0.16, 0.78), ("short_mid_wicket", 0.30, 0.44),
            ("point", 0.86, 0.52), ("third", 0.80, 0.80),
            ("mid_off", 0.58, 0.24), ("mid_on", 0.42, 0.24),
            ("long_on", 0.44, 0.06),
        ],
    },
    "fourth_stump_catchers": {
        "label": "Fourth-stump catchers",
        "positions": [
            ("slip", 0.66, 0.78), ("second_slip", 0.70, 0.76),
            ("third_slip", 0.74, 0.74), ("gully", 0.80, 0.68),
            ("point", 0.86, 0.52), ("cover", 0.76, 0.40),
            ("mid_off", 0.58, 0.24), ("mid_on", 0.42, 0.24),
            ("mid_wicket", 0.26, 0.46),
        ],
    },
}

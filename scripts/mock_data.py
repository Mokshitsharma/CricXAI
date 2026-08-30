"""Deterministic mock ODI data generator for CricXAI.

Live scraping of ESPNcricinfo is unreliable from some networks and its legal
posture for scale is unsettled (see docs/PHASES.md, ADR-003). To unblock
model / API / UI work we simulate a self-consistent ODI dataset:

- 10 international teams, each with a ~15-player *illustrative* "probable 2027
  World Cup" squad (skills are made up, not scouting data).
- A phase-aware ball-by-ball simulator: bowler selection by phase, length /
  line sampled from each bowler's tendencies, a dismissal probability driven
  by batter-vs-bowler skill, delivery danger, batter weaknesses and chase
  pressure, then an outcome multinomial and a length/line-conditioned
  dismissal type.

Output columns are exactly what ``scripts/nlp_parser.py`` produces, so
``scripts/build_features.py`` consumes the result unchanged. Every row is
tagged ``source="mock"`` and every match ``series_id="MOCK"``.

Usage::

    python -m scripts.mock_data --num-matches 100 --seed 42
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.utils.cricket_constants import (
    BALL_LENGTHS,
    BALL_LINES,
    phase_from_over,
)
from app.utils.file_io import write_frame
from app.utils.logger import get_logger

DEFAULT_OUTPUT_DIR = Path("data/processed")
BALLS_PER_OVER = 6
TOTAL_OVERS = 50
MAX_WICKETS = 10
MAX_OVERS_PER_BOWLER = 10
SERIES_ID = "MOCK"

VENUES = [
    "Wankhede Stadium, Mumbai",
    "MCG, Melbourne",
    "Lord's, London",
    "Newlands, Cape Town",
    "Eden Park, Auckland",
    "Gaddafi Stadium, Lahore",
    "R.Premadasa Stadium, Colombo",
    "Shere Bangla Stadium, Dhaka",
    "Zayed Cricket Stadium, Abu Dhabi",
    "Kensington Oval, Bridgetown",
]

# ---------------------------------------------------------------------------
# Squads. (name, role, hand, bowler_type, bat_skill, bowl_skill)
#   role: bat | wk | allround | bowl
#   hand: right | left  (batting hand)
#   bowler_type: one of cricket_constants.BOWLER_TYPES, or None
#   skills in [0, 1]; illustrative only (see module docstring).
# ---------------------------------------------------------------------------

Player = tuple[str, str, str, str | None, float, float]

SQUADS: dict[str, list[Player]] = {
    "India": [
        ("Rohit Sharma", "bat", "right", None, 0.86, 0.10),
        ("Shubman Gill", "bat", "right", None, 0.84, 0.10),
        ("Virat Kohli", "bat", "right", None, 0.88, 0.10),
        ("Shreyas Iyer", "bat", "right", None, 0.78, 0.12),
        ("KL Rahul", "wk", "right", None, 0.80, 0.05),
        ("Hardik Pandya", "allround", "right", "pace_right_arm", 0.74, 0.72),
        ("Ravindra Jadeja", "allround", "left", "left_arm_spin", 0.66, 0.82),
        ("Axar Patel", "allround", "left", "left_arm_spin", 0.58, 0.78),
        ("Kuldeep Yadav", "bowl", "left", "left_arm_spin", 0.28, 0.86),
        ("Jasprit Bumrah", "bowl", "right", "pace_right_arm", 0.18, 0.94),
        ("Mohammed Siraj", "bowl", "right", "pace_right_arm", 0.20, 0.82),
        ("Mohammed Shami", "bowl", "right", "pace_right_arm", 0.24, 0.86),
        ("Yashasvi Jaiswal", "bat", "left", None, 0.80, 0.10),
        ("Rishabh Pant", "wk", "left", None, 0.79, 0.05),
        ("Washington Sundar", "allround", "right", "off_spin", 0.55, 0.74),
    ],
    "Australia": [
        ("Travis Head", "bat", "left", "off_spin", 0.83, 0.45),
        ("Mitchell Marsh", "allround", "right", "pace_right_arm", 0.77, 0.62),
        ("Steve Smith", "bat", "right", "leg_spin", 0.85, 0.30),
        ("Marnus Labuschagne", "bat", "right", "leg_spin", 0.76, 0.35),
        ("Josh Inglis", "wk", "right", None, 0.74, 0.05),
        ("Glenn Maxwell", "allround", "right", "off_spin", 0.78, 0.66),
        ("Marcus Stoinis", "allround", "right", "pace_right_arm", 0.70, 0.60),
        ("Alex Carey", "wk", "left", None, 0.71, 0.05),
        ("Pat Cummins", "bowl", "right", "pace_right_arm", 0.34, 0.90),
        ("Mitchell Starc", "bowl", "left", "pace_left_arm", 0.30, 0.92),
        ("Josh Hazlewood", "bowl", "right", "pace_right_arm", 0.16, 0.88),
        ("Adam Zampa", "bowl", "right", "leg_spin", 0.22, 0.85),
        ("Cameron Green", "allround", "right", "pace_right_arm", 0.68, 0.64),
        ("Sean Abbott", "bowl", "right", "pace_right_arm", 0.30, 0.78),
        ("Nathan Ellis", "bowl", "right", "pace_right_arm", 0.24, 0.79),
    ],
    "England": [
        ("Phil Salt", "wk", "right", None, 0.78, 0.05),
        ("Ben Duckett", "bat", "left", None, 0.79, 0.05),
        ("Joe Root", "bat", "right", "off_spin", 0.86, 0.40),
        ("Harry Brook", "bat", "right", None, 0.82, 0.15),
        ("Jos Buttler", "wk", "right", None, 0.83, 0.05),
        ("Liam Livingstone", "allround", "right", "leg_spin", 0.71, 0.62),
        ("Jacob Bethell", "allround", "left", "left_arm_spin", 0.64, 0.60),
        ("Sam Curran", "allround", "left", "pace_left_arm", 0.60, 0.68),
        ("Jofra Archer", "bowl", "right", "pace_right_arm", 0.26, 0.89),
        ("Adil Rashid", "bowl", "right", "leg_spin", 0.22, 0.86),
        ("Mark Wood", "bowl", "right", "pace_right_arm", 0.24, 0.85),
        ("Brydon Carse", "bowl", "right", "pace_right_arm", 0.34, 0.80),
        ("Will Jacks", "allround", "right", "off_spin", 0.66, 0.58),
        ("Gus Atkinson", "bowl", "right", "pace_right_arm", 0.30, 0.80),
        ("Reece Topley", "bowl", "left", "pace_left_arm", 0.18, 0.80),
    ],
    "South Africa": [
        ("Ryan Rickelton", "wk", "left", None, 0.75, 0.05),
        ("Aiden Markram", "bat", "right", "off_spin", 0.80, 0.52),
        ("Temba Bavuma", "bat", "right", None, 0.77, 0.10),
        ("Rassie van der Dussen", "bat", "right", None, 0.78, 0.10),
        ("Heinrich Klaasen", "wk", "right", None, 0.83, 0.05),
        ("David Miller", "bat", "left", None, 0.76, 0.10),
        ("Wiaan Mulder", "allround", "right", "pace_right_arm", 0.62, 0.66),
        ("Marco Jansen", "allround", "left", "pace_left_arm", 0.52, 0.80),
        ("Kagiso Rabada", "bowl", "right", "pace_right_arm", 0.28, 0.91),
        ("Keshav Maharaj", "bowl", "left", "left_arm_spin", 0.30, 0.84),
        ("Lungi Ngidi", "bowl", "right", "pace_right_arm", 0.18, 0.82),
        ("Tabraiz Shamsi", "bowl", "left", "left_arm_spin", 0.16, 0.85),
        ("Tristan Stubbs", "bat", "right", None, 0.74, 0.20),
        ("Gerald Coetzee", "bowl", "right", "pace_right_arm", 0.32, 0.79),
        ("Nandre Burger", "bowl", "left", "pace_left_arm", 0.20, 0.78),
    ],
    "New Zealand": [
        ("Devon Conway", "bat", "left", None, 0.80, 0.05),
        ("Will Young", "bat", "right", None, 0.74, 0.05),
        ("Kane Williamson", "bat", "right", "off_spin", 0.86, 0.35),
        ("Daryl Mitchell", "allround", "right", "pace_right_arm", 0.78, 0.55),
        ("Tom Latham", "wk", "left", None, 0.76, 0.05),
        ("Glenn Phillips", "allround", "right", "off_spin", 0.74, 0.62),
        ("Mark Chapman", "bat", "left", "left_arm_spin", 0.68, 0.40),
        ("Michael Bracewell", "allround", "right", "off_spin", 0.60, 0.72),
        ("Mitchell Santner", "allround", "left", "left_arm_spin", 0.54, 0.80),
        ("Matt Henry", "bowl", "right", "pace_right_arm", 0.26, 0.87),
        ("Trent Boult", "bowl", "left", "pace_left_arm", 0.22, 0.89),
        ("Lockie Ferguson", "bowl", "right", "pace_right_arm", 0.24, 0.84),
        ("William O'Rourke", "bowl", "right", "pace_right_arm", 0.20, 0.81),
        ("Rachin Ravindra", "allround", "left", "left_arm_spin", 0.76, 0.58),
        ("Ish Sodhi", "bowl", "right", "leg_spin", 0.18, 0.80),
    ],
    "Pakistan": [
        ("Saim Ayub", "allround", "left", "leg_spin", 0.76, 0.48),
        ("Fakhar Zaman", "bat", "left", None, 0.77, 0.20),
        ("Babar Azam", "bat", "right", None, 0.85, 0.10),
        ("Mohammad Rizwan", "wk", "right", None, 0.80, 0.05),
        ("Saud Shakeel", "bat", "left", None, 0.74, 0.10),
        ("Salman Agha", "allround", "right", "off_spin", 0.68, 0.64),
        ("Shadab Khan", "allround", "right", "leg_spin", 0.58, 0.74),
        ("Mohammad Nawaz", "allround", "left", "left_arm_spin", 0.56, 0.72),
        ("Shaheen Afridi", "bowl", "left", "pace_left_arm", 0.34, 0.90),
        ("Naseem Shah", "bowl", "right", "pace_right_arm", 0.24, 0.86),
        ("Haris Rauf", "bowl", "right", "pace_right_arm", 0.20, 0.84),
        ("Abrar Ahmed", "bowl", "right", "leg_spin", 0.16, 0.83),
        ("Kamran Ghulam", "bat", "right", "off_spin", 0.70, 0.30),
        ("Naseem Khan", "bowl", "right", "pace_right_arm", 0.22, 0.78),
        ("Usama Mir", "bowl", "right", "leg_spin", 0.20, 0.79),
    ],
    "Sri Lanka": [
        ("Pathum Nissanka", "bat", "right", None, 0.79, 0.05),
        ("Kusal Mendis", "wk", "right", None, 0.77, 0.05),
        ("Kusal Perera", "bat", "left", None, 0.73, 0.05),
        ("Charith Asalanka", "allround", "left", "off_spin", 0.75, 0.55),
        ("Sadeera Samarawickrama", "wk", "right", None, 0.71, 0.05),
        ("Janith Liyanage", "bat", "right", "off_spin", 0.66, 0.35),
        ("Dunith Wellalage", "allround", "left", "left_arm_spin", 0.58, 0.74),
        ("Wanindu Hasaranga", "allround", "right", "leg_spin", 0.60, 0.82),
        ("Maheesh Theekshana", "bowl", "right", "off_spin", 0.24, 0.83),
        ("Nuwan Thushara", "bowl", "right", "pace_right_arm", 0.20, 0.79),
        ("Asitha Fernando", "bowl", "right", "pace_right_arm", 0.22, 0.80),
        ("Matheesha Pathirana", "bowl", "right", "pace_right_arm", 0.18, 0.84),
        ("Avishka Fernando", "bat", "right", None, 0.72, 0.10),
        ("Dushmantha Chameera", "bowl", "right", "pace_right_arm", 0.24, 0.79),
        ("Jeffrey Vandersay", "bowl", "right", "leg_spin", 0.16, 0.77),
    ],
    "Bangladesh": [
        ("Tanzid Hasan", "bat", "left", None, 0.72, 0.05),
        ("Litton Das", "wk", "right", None, 0.74, 0.05),
        ("Najmul Hossain Shanto", "bat", "left", "off_spin", 0.73, 0.30),
        ("Towhid Hridoy", "bat", "right", None, 0.72, 0.10),
        ("Mushfiqur Rahim", "wk", "right", None, 0.73, 0.05),
        ("Mahmudullah", "allround", "right", "off_spin", 0.68, 0.52),
        ("Mehidy Hasan Miraz", "allround", "right", "off_spin", 0.60, 0.78),
        ("Shakib Al Hasan", "allround", "left", "left_arm_spin", 0.72, 0.80),
        ("Rishad Hossain", "bowl", "right", "leg_spin", 0.30, 0.74),
        ("Taskin Ahmed", "bowl", "right", "pace_right_arm", 0.26, 0.83),
        ("Mustafizur Rahman", "bowl", "left", "pace_left_arm", 0.20, 0.82),
        ("Nahid Rana", "bowl", "right", "pace_right_arm", 0.18, 0.81),
        ("Parvez Hossain Emon", "bat", "left", None, 0.68, 0.05),
        ("Tanzim Hasan Sakib", "bowl", "right", "pace_right_arm", 0.28, 0.77),
        ("Nasum Ahmed", "bowl", "left", "left_arm_spin", 0.22, 0.75),
    ],
    "Afghanistan": [
        ("Rahmanullah Gurbaz", "wk", "right", None, 0.76, 0.05),
        ("Ibrahim Zadran", "bat", "right", None, 0.77, 0.05),
        ("Sediqullah Atal", "bat", "left", None, 0.70, 0.05),
        ("Rahmat Shah", "bat", "right", "leg_spin", 0.74, 0.35),
        ("Hashmatullah Shahidi", "bat", "left", None, 0.71, 0.10),
        ("Azmatullah Omarzai", "allround", "right", "pace_right_arm", 0.68, 0.72),
        ("Mohammad Nabi", "allround", "right", "off_spin", 0.64, 0.70),
        ("Rashid Khan", "allround", "right", "leg_spin", 0.56, 0.90),
        ("Gulbadin Naib", "allround", "right", "pace_right_arm", 0.58, 0.58),
        ("Noor Ahmad", "bowl", "left", "left_arm_spin", 0.24, 0.84),
        ("Fazalhaq Farooqi", "bowl", "left", "pace_left_arm", 0.18, 0.83),
        ("Naveen-ul-Haq", "bowl", "right", "pace_right_arm", 0.22, 0.80),
        ("Ikram Alikhil", "wk", "left", None, 0.66, 0.05),
        ("Mujeeb Ur Rahman", "bowl", "right", "off_spin", 0.16, 0.83),
        ("Nangeyalia Kharote", "bowl", "left", "left_arm_spin", 0.20, 0.76),
    ],
    "West Indies": [
        ("Brandon King", "bat", "right", None, 0.74, 0.05),
        ("Evin Lewis", "bat", "left", None, 0.73, 0.05),
        ("Keacy Carty", "bat", "right", None, 0.72, 0.10),
        ("Shai Hope", "wk", "right", None, 0.80, 0.05),
        ("Sherfane Rutherford", "bat", "left", "pace_right_arm", 0.74, 0.35),
        ("Roston Chase", "allround", "right", "off_spin", 0.66, 0.68),
        ("Rovman Powell", "bat", "right", None, 0.72, 0.10),
        ("Romario Shepherd", "allround", "right", "pace_right_arm", 0.62, 0.66),
        ("Gudakesh Motie", "bowl", "left", "left_arm_spin", 0.28, 0.80),
        ("Alzarri Joseph", "bowl", "right", "pace_right_arm", 0.30, 0.84),
        ("Jayden Seales", "bowl", "right", "pace_right_arm", 0.20, 0.82),
        ("Shamar Joseph", "bowl", "right", "pace_right_arm", 0.24, 0.83),
        ("Brandon Hemraj", "bat", "right", None, 0.66, 0.05),
        ("Matthew Forde", "allround", "right", "pace_right_arm", 0.44, 0.72),
        ("Akeal Hosein", "bowl", "left", "left_arm_spin", 0.26, 0.79),
    ],
}

SPIN_TYPES = {"off_spin", "leg_spin", "left_arm_spin"}
PACE_TYPES = {"pace_right_arm", "pace_left_arm"}


# ---------------------------------------------------------------------------
# Delivery tendencies and danger
# ---------------------------------------------------------------------------

# P(length | bowler family, phase). Rows sum to 1.
_PACE_LENGTH = {
    "powerplay": {"yorker": 0.03, "full": 0.22, "good": 0.55, "short": 0.15, "bouncer": 0.05},
    "early_middle": {"yorker": 0.03, "full": 0.20, "good": 0.57, "short": 0.15, "bouncer": 0.05},
    "middle": {"yorker": 0.04, "full": 0.20, "good": 0.55, "short": 0.16, "bouncer": 0.05},
    "late_middle": {"yorker": 0.08, "full": 0.24, "good": 0.45, "short": 0.17, "bouncer": 0.06},
    "death": {"yorker": 0.22, "full": 0.30, "good": 0.24, "short": 0.16, "bouncer": 0.08},
}
_SPIN_LENGTH = {
    "powerplay": {"yorker": 0.01, "full": 0.30, "good": 0.60, "short": 0.08, "bouncer": 0.01},
    "early_middle": {"yorker": 0.01, "full": 0.28, "good": 0.63, "short": 0.07, "bouncer": 0.01},
    "middle": {"yorker": 0.01, "full": 0.27, "good": 0.64, "short": 0.07, "bouncer": 0.01},
    "late_middle": {"yorker": 0.03, "full": 0.33, "good": 0.55, "short": 0.08, "bouncer": 0.01},
    "death": {"yorker": 0.10, "full": 0.40, "good": 0.38, "short": 0.11, "bouncer": 0.01},
}

# P(line | bowler type, phase). Rows sum to 1.
def _line_profile(bowler_type: str, phase: str) -> dict[str, float]:
    if bowler_type in PACE_TYPES:
        base = {
            "wide_outside_off": 0.10, "outside_off": 0.40, "off_stump": 0.24,
            "middle_stump": 0.14, "leg_stump": 0.08, "down_leg": 0.03, "wide_down_leg": 0.01,
        }
        if phase == "death":
            base = {
                "wide_outside_off": 0.20, "outside_off": 0.30, "off_stump": 0.26,
                "middle_stump": 0.14, "leg_stump": 0.07, "down_leg": 0.02, "wide_down_leg": 0.01,
            }
        return base
    # spin
    return {
        "wide_outside_off": 0.06, "outside_off": 0.30, "off_stump": 0.30,
        "middle_stump": 0.22, "leg_stump": 0.09, "down_leg": 0.02, "wide_down_leg": 0.01,
    }


# (wicket multiplier, expected-runs baseline) per (length, line).
_DANGER: dict[tuple[str, str], tuple[float, float]] = {}
def _fill_danger() -> None:
    for length in BALL_LENGTHS:
        for line in BALL_LINES:
            wkt, runs = 1.0, 0.9
            if length == "yorker":
                wkt, runs = (1.6, 0.7) if line in ("off_stump", "middle_stump", "leg_stump") else (0.7, 1.1)
            elif length == "full":
                if line in ("off_stump", "middle_stump", "leg_stump"):
                    wkt, runs = 1.5, 1.0
                elif line in ("outside_off",):
                    wkt, runs = 1.1, 1.25
                else:
                    wkt, runs = 0.7, 1.5
            elif length == "good":
                if line in ("outside_off", "off_stump"):
                    wkt, runs = 1.2, 0.75
                elif line in ("wide_outside_off",):
                    wkt, runs = 0.8, 1.1
                else:
                    wkt, runs = 0.9, 0.9
            elif length == "short":
                if line in ("wide_outside_off", "outside_off"):
                    wkt, runs = 0.9, 1.35
                elif line in ("off_stump", "middle_stump"):
                    wkt, runs = 1.25, 1.15
                else:
                    wkt, runs = 1.0, 1.2
            elif length == "bouncer":
                wkt, runs = 1.35, 1.25
            if line == "wide_outside_off":
                runs += 0.25
            if line in ("down_leg", "wide_down_leg"):
                wkt, runs = wkt * 0.5, runs + 0.4
            _DANGER[(length, line)] = (wkt, runs)
_fill_danger()


@dataclass
class PlayerCard:
    name: str
    team: str
    role: str
    hand: str
    bowler_type: str | None
    bat_skill: float
    bowl_skill: float
    weakness_length: str          # a length this batter is extra vulnerable to
    weak_vs_spin: bool            # struggles against spin
    aggression_bias: float        # -0.1..+0.15 personal tempo tweak


def build_player_cards(rng: random.Random) -> dict[str, PlayerCard]:
    cards: dict[str, PlayerCard] = {}
    for team, squad in SQUADS.items():
        for name, role, hand, bt, bat, bowl in squad:
            weakness_length = rng.choice(["short", "bouncer", "full", "yorker", "good"])
            weak_vs_spin = rng.random() < 0.35
            aggression_bias = round(rng.uniform(-0.10, 0.15), 3)
            cards[name] = PlayerCard(
                name=name, team=team, role=role, hand=hand, bowler_type=bt,
                bat_skill=bat, bowl_skill=bowl, weakness_length=weakness_length,
                weak_vs_spin=weak_vs_spin, aggression_bias=aggression_bias,
            )
    return cards


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _weighted_choice(rng: random.Random, table: dict[str, float]) -> str:
    keys = list(table.keys())
    weights = list(table.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def _batting_order(squad: list[Player]) -> list[str]:
    """Top 6 batters/keepers/allrounders first, then the rest."""
    def key(p: Player) -> tuple[int, float]:
        _name, role, *_rest, bat, _bowl = p
        rank = {"bat": 0, "wk": 1, "allround": 2, "bowl": 3}[role]
        return (rank, -bat)
    ordered = [p[0] for p in sorted(squad, key=key)]
    return ordered[:11]


def _bowling_options(squad: list[Player]) -> list[str]:
    opts = [p[0] for p in squad if p[3] is not None and p[5] >= 0.5]
    return opts[:8] if len(opts) >= 5 else [p[0] for p in squad if p[3] is not None][:6]


def _pick_bowler(
    rng: random.Random,
    options: list[str],
    cards: dict[str, PlayerCard],
    phase: str,
    overs_bowled: dict[str, int],
    last_bowler: str | None,
) -> str:
    def eligible(name: str) -> bool:
        return overs_bowled.get(name, 0) < MAX_OVERS_PER_BOWLER and name != last_bowler

    pool = [n for n in options if eligible(n)] or [n for n in options if n != last_bowler] or options
    weights = []
    for name in pool:
        bt = cards[name].bowler_type
        w = cards[name].bowl_skill
        if phase in ("powerplay", "death") and bt in PACE_TYPES:
            w *= 1.8
        if phase in ("early_middle", "middle", "late_middle") and bt in SPIN_TYPES:
            w *= 1.7
        weights.append(max(w, 0.05))
    return rng.choices(pool, weights=weights, k=1)[0]


def _dismissal_type(rng: random.Random, length: str, line: str, bowler_type: str | None) -> str:
    if rng.random() < 0.05:
        return "run_out"
    straight = line in ("off_stump", "middle_stump", "leg_stump")
    if length in ("full", "yorker") and straight:
        return rng.choices(["bowled", "lbw", "caught"], weights=[0.5, 0.35, 0.15])[0]
    if length in ("short", "bouncer"):
        return rng.choices(["caught", "hit_wicket"], weights=[0.94, 0.06])[0]
    if bowler_type in SPIN_TYPES:
        if straight:
            return rng.choices(["bowled", "lbw", "stumped", "caught"], weights=[0.34, 0.30, 0.16, 0.20])[0]
        return rng.choices(["caught", "stumped", "bowled"], weights=[0.62, 0.20, 0.18])[0]
    # good / full outside off, pace
    return rng.choices(["caught", "bowled", "lbw"], weights=[0.78, 0.14, 0.08])[0]


def _shot_type(rng: random.Random, length: str, line: str, outcome: str) -> str:
    if outcome == "dot":
        return rng.choice(["defend", "leave", "defend"])
    if outcome == "wicket":
        return rng.choice(["edge", "loft", "pull", "defend", "flick"])
    if outcome in ("four", "six"):
        if length in ("short", "bouncer"):
            return rng.choice(["pull", "hook", "cut"])
        if line in ("leg_stump", "down_leg", "middle_stump"):
            return rng.choice(["flick", "sweep", "loft"])
        return rng.choice(["cover_drive", "straight_drive", "cut", "loft"])
    if length in ("short", "bouncer"):
        return rng.choice(["pull", "cut", "defend"])
    if line in ("leg_stump", "down_leg"):
        return rng.choice(["flick", "glance", "sweep"])
    return rng.choice(["cover_drive", "straight_drive", "defend", "flick"])


def _aggression(phase: str, chasing: bool, pressure: float, bias: float) -> float:
    base = {
        "powerplay": 0.52, "early_middle": 0.40, "middle": 0.42,
        "late_middle": 0.58, "death": 0.82,
    }[phase]
    if chasing:
        base += min(max(pressure, 0.0), 8.0) * 0.02
    return float(np.clip(base + bias, 0.15, 0.98))


def _runs_distribution(exp_runs: float, aggression: float) -> dict[int, float]:
    """A crude multinomial over {0,1,2,3,4,6} shaped by expected runs + tempo."""
    boundary = np.clip(0.05 + 0.11 * exp_runs * (0.6 + aggression), 0.02, 0.42)
    six = boundary * (0.25 + 0.4 * aggression)
    four = boundary - six
    three = 0.01
    two = np.clip(0.08 + 0.05 * exp_runs, 0.03, 0.20)
    one = np.clip(0.30 + 0.15 * (1 - aggression), 0.20, 0.52)
    dot = max(1.0 - (four + six + three + two + one), 0.05)
    return {0: dot, 1: one, 2: two, 3: three, 4: four, 6: six}


def simulate_innings(
    rng: random.Random,
    match_id: str,
    innings: int,
    batting_squad: list[Player],
    bowling_squad: list[Player],
    cards: dict[str, PlayerCard],
    target: int | None,
    batting_team: str = "",
) -> tuple[list[dict], int, int]:
    order = _batting_order(batting_squad)
    bowl_options = _bowling_options(bowling_squad)

    rows: list[dict] = []
    striker_idx, non_striker_idx = 0, 1
    next_batter_idx = 2
    score, wickets = 0, 0
    overs_bowled: dict[str, int] = {}
    last_bowler: str | None = None

    for over in range(TOTAL_OVERS):
        if wickets >= MAX_WICKETS:
            break
        phase = phase_from_over(over)
        bowler = _pick_bowler(rng, bowl_options, cards, phase, overs_bowled, last_bowler)
        overs_bowled[bowler] = overs_bowled.get(bowler, 0) + 1
        last_bowler = bowler
        b_card = cards[bowler]

        ball_in_over = 0
        legal_balls = 0
        while legal_balls < BALLS_PER_OVER:
            if wickets >= MAX_WICKETS:
                break
            striker = order[striker_idx]
            s_card = cards[striker]

            chasing = innings == 2
            overs_done = over + legal_balls / BALLS_PER_OVER
            overs_left = max(TOTAL_OVERS - overs_done, 0.1)
            crr = score / overs_done if overs_done > 0 else 6.0
            rrr = (target - score) / overs_left if (chasing and target is not None) else 0.0
            pressure = max(rrr - crr, 0.0) + (wickets / 10.0) * 2.0 if chasing else 0.0

            length_tbl = _PACE_LENGTH if b_card.bowler_type in PACE_TYPES else _SPIN_LENGTH
            length = _weighted_choice(rng, length_tbl[phase])
            line = _weighted_choice(rng, _line_profile(b_card.bowler_type or "off_spin", phase))

            # ~3.5% wides (not a legal ball, striker keeps strike).
            if rng.random() < 0.035:
                score += 1
                ball_in_over += 1
                rows.append(_row(match_id, innings, over, ball_in_over, striker, bowler,
                                 1, length, line, "glance", "wide", False, None, None, batting_team))
                continue

            legal_balls += 1
            ball_in_over += 1

            wkt_mult, exp_runs = _DANGER[(length, line)]
            skill_gap = s_card.bat_skill - b_card.bowl_skill
            p_wkt = 0.030 * wkt_mult
            p_wkt *= float(np.clip(1.0 - skill_gap * 1.4, 0.25, 2.6))
            if length == s_card.weakness_length:
                p_wkt *= 1.7
            if s_card.weak_vs_spin and b_card.bowler_type in SPIN_TYPES:
                p_wkt *= 1.45
            aggression = _aggression(phase, chasing, pressure, s_card.aggression_bias)
            p_wkt *= 0.85 + aggression * 0.7
            p_wkt *= 1.0 + min(pressure, 8.0) * 0.03
            p_wkt = float(np.clip(p_wkt, 0.003, 0.55))

            if rng.random() < p_wkt:
                wickets += 1
                dtype = _dismissal_type(rng, length, line, b_card.bowler_type)
                runs = 1 if dtype == "run_out" else 0
                score += runs
                shot = _shot_type(rng, length, line, "wicket")
                rows.append(_row(match_id, innings, over, ball_in_over, striker, bowler,
                                 runs, length, line, shot, "wicket", True, dtype, striker, batting_team))
                if next_batter_idx < len(order):
                    striker_idx = next_batter_idx
                    next_batter_idx += 1
                else:
                    striker_idx = -1
                if striker_idx == -1:
                    break
                continue

            eff_exp = exp_runs * (0.7 + 0.7 * aggression) * float(np.clip(1.0 + skill_gap, 0.5, 1.8))
            dist = _runs_distribution(eff_exp, aggression)
            runs = rng.choices(list(dist.keys()), weights=list(dist.values()), k=1)[0]
            score += runs
            outcome = {0: "dot", 1: "single", 2: "two", 3: "three", 4: "four", 6: "six"}[runs]
            shot = _shot_type(rng, length, line, outcome)
            rows.append(_row(match_id, innings, over, ball_in_over, striker, bowler,
                             runs, length, line, shot, outcome, False, None, None, batting_team))

            if runs % 2 == 1:
                striker_idx, non_striker_idx = non_striker_idx, striker_idx

            if chasing and target is not None and score >= target:
                return rows, score, wickets

        striker_idx, non_striker_idx = non_striker_idx, striker_idx

    return rows, score, wickets


def _row(match_id, innings, over, ball_in_over, batsman, bowler, total_runs,
         ball_length, ball_line, shot_type, outcome, is_wicket, dismissal_type, player_out,
         batting_team="") -> dict:
    return {
        "match_id": match_id,
        "innings": innings,
        "over": over,
        "ball_in_over": ball_in_over,
        "batsman": batsman,
        "bowler": bowler,
        "text": f"{ball_length} delivery, {ball_line.replace('_', ' ')}; {outcome}",
        "total_runs": total_runs,
        "ball_length": ball_length,
        "ball_line": ball_line,
        "shot_type": shot_type,
        "outcome": outcome,
        "is_wicket": is_wicket,
        "dismissal_type": dismissal_type,
        "player_out": player_out,
        "batting_team": batting_team,
        "source": "mock",
    }


def simulate_match(
    rng: random.Random, match_index: int, team_a: str, team_b: str,
    cards: dict[str, PlayerCard],
) -> tuple[list[dict], dict]:
    match_id = f"MOCK{match_index:04d}"
    if rng.random() < 0.5:
        team_a, team_b = team_b, team_a
    squad_a, squad_b = SQUADS[team_a], SQUADS[team_b]

    rows1, score1, wk1 = simulate_innings(
        rng, match_id, 1, squad_a, squad_b, cards, target=None, batting_team=team_a
    )
    rows2, score2, wk2 = simulate_innings(
        rng, match_id, 2, squad_b, squad_a, cards, target=score1 + 1, batting_team=team_b
    )
    rows = rows1 + rows2

    if score2 >= score1 + 1:
        result = f"{team_b} won by {MAX_WICKETS - wk2} wickets"
    elif score2 == score1:
        result = "Match tied"
    else:
        result = f"{team_a} won by {score1 - score2} runs"

    meta = {
        "match_id": match_id,
        "series_id": SERIES_ID,
        "source": "mock",
        "teams": f"{team_a} vs {team_b}",
        "home_team": team_a,
        "away_team": team_b,
        "venue": VENUES[match_index % len(VENUES)],
        "date": str(np.datetime64("2026-01-05") + np.timedelta64(match_index * 2, "D")),
        "result": result,
        "innings1_runs": score1,
        "innings2_runs": score2,
        "delivery_count": len(rows),
    }
    return rows, meta


def generate(num_matches: int, seed: int, logger=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger = logger or get_logger(__name__)
    rng = random.Random(seed)
    np.random.seed(seed)
    cards = build_player_cards(random.Random(seed + 1))

    teams = list(SQUADS.keys())
    all_rows: list[dict] = []
    all_meta: list[dict] = []
    for i in range(1, num_matches + 1):
        a, b = rng.sample(teams, 2)
        rows, meta = simulate_match(rng, i, a, b, cards)
        all_rows.extend(rows)
        all_meta.append(meta)

    deliveries = pd.DataFrame(all_rows)
    matches = pd.DataFrame(all_meta)
    logger.info(
        "Generated %s matches, %s deliveries, %s wickets",
        len(matches), len(deliveries), int(deliveries["is_wicket"].sum()),
    )
    return deliveries, matches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic mock ODI data for CricXAI.")
    parser.add_argument("--num-matches", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = get_logger(__name__)
    deliveries, matches = generate(args.num_matches, args.seed, logger=logger)

    write_frame(deliveries, args.output_dir / "deliveries")
    write_frame(matches, args.output_dir / "matches")
    logger.info("Wrote deliveries + matches (.csv + .parquet) to %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

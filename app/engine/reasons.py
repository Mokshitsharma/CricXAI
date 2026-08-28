"""Turn SHAP contributions into cricket-language reasons.

Each recommendation card shows 3-4 plain sentences, ordered by contribution
magnitude, using dataset-average deltas where we have them. Templates are
deliberately conservative — if a feature has no template it is skipped rather
than rendered as a raw name.
"""

from __future__ import annotations

from app.utils.cricket_constants import BALL_LENGTHS, DISMISSAL_TYPES

MAX_REASONS = 4


def _fmt_pct(v: float) -> str:
    return f"{v:.0f}%"


def _a(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _delta_clause(value: float, mean: float | None) -> str:
    if mean is None:
        return ""
    diff = value - mean
    if abs(diff) < 3:
        return f" (about average, {_fmt_pct(mean)})"
    direction = "above" if diff > 0 else "below"
    return f" ({_fmt_pct(abs(diff))} {direction} the {_fmt_pct(mean)} average)"


def _is_notable(value: float, mean: float | None) -> bool:
    """A historical rate is only a *reason* if it stands apart from the average."""
    return mean is None or abs(value - mean) >= 4


def _sentence(name: str, value: float, shap_value: float, ctx: dict, means: dict) -> str | None:
    mean = means.get(name)
    increases = shap_value > 0

    if name.startswith("hist_ball_length_"):
        length = name[len("hist_ball_length_"):-len("_pct")]
        if length in BALL_LENGTHS and increases and _is_notable(value, mean):
            return (
                f"{_fmt_pct(value)} of his dismissals come to the {length} ball"
                f"{_delta_clause(value, mean)}."
            )
    if name.startswith("hist_ball_line_"):
        line = name[len("hist_ball_line_"):-len("_pct")].replace("_", " ")
        if increases and _is_notable(value, mean):
            return (
                f"{_fmt_pct(value)} of his dismissals come from {_a(line)} {line} line"
                f"{_delta_clause(value, mean)}."
            )
    if name.startswith("hist_dismissal_type_"):
        dt = name[len("hist_dismissal_type_"):-len("_pct")]
        if dt in DISMISSAL_TYPES and increases and _is_notable(value, mean):
            return (
                f"He is {dt.replace('_', ' ')} on {_fmt_pct(value)} of his dismissals"
                f"{_delta_clause(value, mean)}."
            )
    if name == "pressure_index" and ctx.get("pressure_index", 0) >= 3 and increases:
        return (
            f"Under chase pressure (index {ctx['pressure_index']:.1f}), "
            "his dismissal risk rises."
        )
    if name == "ball_length_encoded" and increases:
        return f"The {ctx.get('length', 'chosen')} length is a high-danger option in this situation."
    if name == "ball_line_encoded" and increases:
        line = str(ctx.get("line", "chosen")).replace("_", " ")
        return f"The {line} line is where he is most exposed here."
    if name == "phase_encoded" and increases:
        return f"He is more dismissal-prone in the {ctx.get('phase', 'this')} overs."
    if name == "batsman_dot_pct" and value >= 40 and increases:
        return f"He has been tied down (dot {_fmt_pct(value)}); the pressure to score lifts his risk."
    if name == "batsman_strike_rate" and value >= 110 and increases:
        return f"He is going hard (strike rate {value:.0f}), so a wicket ball is likelier to be taken."
    if name == "hist_avg_under_pressure" and not increases:
        return f"He averages only {value:.0f} under pressure."
    if name == "hist_phase_avg" and not increases:
        return f"His average in this phase is {value:.0f}."
    if name == "bowler_wickets_so_far" and value >= 1 and increases:
        return f"The bowler already has {value:.0f} wicket(s) this innings."
    if name == "innings_wickets" and increases:
        return f"With {value:.0f} down, a wicket now opens up the lower order."
    return None


def build_reasons(
    contributions: list[tuple[str, float, float]],
    context: dict,
    feature_means: dict[str, float] | None = None,
) -> list[str]:
    means = feature_means or {}
    seen: set[str] = set()
    out: list[str] = []
    for name, value, shap_value in contributions:
        sentence = _sentence(name, value, shap_value, context, means)
        if sentence and sentence not in seen:
            seen.add(sentence)
            out.append(sentence)
        if len(out) >= MAX_REASONS:
            break
    if not out:
        out.append(
            "This delivery maximises modelled wicket probability for the situation, "
            "with acceptable expected runs."
        )
    return out

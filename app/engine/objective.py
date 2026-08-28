"""Turn (P(wicket), E[runs]) into a single rank-able score, per phase.

At the death a wicket is worth chasing even at some run cost; in the middle
overs containment matters more. Weights are deliberately simple and live
here so they are easy to tune against the backtest once real data exists
(docs/TRD.md §7).
"""

from __future__ import annotations

# phase -> (wicket_weight, runs_weight)
PHASE_WEIGHTS: dict[str, tuple[float, float]] = {
    "powerplay": (1.0, 0.55),
    "early_middle": (1.0, 0.45),
    "middle": (1.0, 0.40),
    "late_middle": (1.0, 0.60),
    "death": (1.0, 0.35),
}

# Rough per-ball run scale used to normalise E[runs] into the same ballpark
# as a wicket probability before weighting.
_RUNS_SCALE = 3.0


def score_candidate(
    p_wicket: float, e_runs: float, phase: str, low_sample_penalty: float = 0.0
) -> float:
    w_wicket, w_runs = PHASE_WEIGHTS.get(phase, (1.0, 0.45))
    return (
        w_wicket * p_wicket
        - w_runs * (e_runs / _RUNS_SCALE)
        - low_sample_penalty
    )

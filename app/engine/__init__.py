"""Recommendation engine: score the candidate delivery grid and rank it.

Framework-free by design (docs/RULES.md R-20) — it takes situation +
batsman features + loaded models and returns ranked, explained
recommendations. The API layer wraps it; a notebook can call it directly.
"""

from app.engine.recommend import Recommendation, recommend, score_grid

__all__ = ["Recommendation", "recommend", "score_grid"]

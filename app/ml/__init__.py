"""Model training, registry and explanation for CricXAI.

Kept framework-free (no FastAPI, no DB): everything here takes DataFrames /
arrays and fitted estimators, so it is usable from a notebook and from the
API alike. See docs/RULES.md R-20.
"""

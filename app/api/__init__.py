"""CricXAI HTTP API (FastAPI).

Owns transport only — validation, serialization, wiring. Business logic
lives in ``app/engine`` and ``app/ml`` (docs/RULES.md R-21). Backed by the
in-memory CSV data layer (``app/api/data.py``) until the Postgres swap in
Phase 3.
"""

"""Match browser: list matches and a ball-by-ball timeline."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["matches"])


def _store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Data store not loaded.")
    return store


@router.get("/matches")
def list_matches(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    store = _store(request)
    return {"matches": store.list_matches(limit=limit)}


@router.get("/matches/{match_id}/timeline")
def match_timeline(request: Request, match_id: str) -> dict:
    store = _store(request)
    timeline = store.match_timeline(match_id)
    if not timeline:
        raise HTTPException(status_code=404, detail=f"Unknown match: {match_id}")
    return {"match_id": match_id, "deliveries": timeline}

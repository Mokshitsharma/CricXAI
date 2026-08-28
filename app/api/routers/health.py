"""Liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> JSONResponse:
    models = getattr(request.app.state, "models", None)
    store = getattr(request.app.state, "store", None)
    ready = models is not None and store is not None
    body = {
        "status": "ready" if ready else "not_ready",
        "models_loaded": models is not None,
        "data_loaded": store is not None,
        "model_version": getattr(models, "version", None),
    }
    return JSONResponse(status_code=200 if ready else 503, content=body)

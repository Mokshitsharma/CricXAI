"""Core endpoints: delivery recommendation and single-delivery dismissal odds."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import (
    DismissalPredictRequest,
    RecommendationRequest,
    RecommendationResponse,
)
from app.api.service import RecommendationService
from app.utils.logger import get_logger

router = APIRouter(tags=["recommendation"])
logger = get_logger("cricxai.api.recommendation")


def _service(request: Request) -> RecommendationService:
    models = getattr(request.app.state, "models", None)
    store = getattr(request.app.state, "store", None)
    if models is None:
        raise HTTPException(status_code=503, detail="Models are not loaded yet.")
    if store is None:
        raise HTTPException(status_code=503, detail="Data store not loaded.")
    return RecommendationService(store, models)


@router.post("/recommendation", response_model=RecommendationResponse)
def recommendation(request: Request, body: RecommendationRequest) -> dict:
    service = _service(request)
    try:
        return service.recommend(body, logger=logger)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Unknown batsman.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/grid")
def grid(request: Request, body: RecommendationRequest) -> dict:
    """Every candidate delivery scored (P wicket + E runs) — drives the heatmap."""
    service = _service(request)
    try:
        return service.grid(body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Unknown batsman.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/predict/dismissal")
def predict_dismissal(request: Request, body: DismissalPredictRequest) -> dict:
    service = _service(request)
    try:
        return service.predict_dismissal(body, logger=logger)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Unknown batsman.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

"""FastAPI application factory and wiring for the CricXAI v1 API."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.data import get_data_store
from app.api.routers import batsmen, health, matches, recommendation, reference
from app.ml.registry import NoActiveModelError, load_active_models
from app.utils.logger import get_logger

logger = get_logger("cricxai.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.models = load_active_models(logger=logger)
        logger.info("Models loaded: %s", app.state.models.version)
    except NoActiveModelError as exc:
        app.state.models = None
        logger.warning("No active models (%s). /readyz will report 503.", exc)

    try:
        app.state.store = get_data_store()
    except FileNotFoundError as exc:
        app.state.store = None
        logger.warning("Data store not available: %s", exc)

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="CricXAI API",
        version="1.0.0",
        description="Prescriptive cricket strategy — delivery recommendations with reasons.",
        openapi_url="/v1/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Request failed validation.",
                    "details": {"errors": jsonable_encoder(exc.errors())},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException):
        code = {400: "bad_request", 404: "not_found", 422: "unprocessable",
                429: "rate_limited", 503: "unavailable"}.get(exc.status_code, "error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": str(exc.detail)}},
        )

    app.include_router(health.router)
    app.include_router(reference.router, prefix="/v1")
    app.include_router(batsmen.router, prefix="/v1")
    app.include_router(matches.router, prefix="/v1")
    app.include_router(recommendation.router, prefix="/v1")

    # Serve the single-file web console at "/" (explicit routes above win).
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="console")

    return app


app = create_app()

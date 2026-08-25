from __future__ import annotations

import math
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import limiter
from app.routers import (
    auth,
    designs,
    estimates,
    health,
    images,
    jobs,
    materials,
    projects,
    regions,
    renders,
    reports,
)

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=settings.app_env)
    try:
        from app.providers.storage.s3 import get_storage

        get_storage().ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        log.warning("storage_unavailable", error=str(exc))
    yield
    log.info("shutdown")


app = FastAPI(
    title="AI Exterior Renovation & Cost Estimation API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_prod else None,
    redoc_url=None,
    openapi_url="/openapi.json" if not settings.is_prod else None,
)


def _sanitize_floats(obj):
    """Replace NaN/Infinity with their repr so the error body can be JSON-encoded.

    A validator that rejects a non-finite input (e.g. region.py's finiteness check) echoes the
    rejected value back in `detail[].input`; Starlette's JSONResponse refuses to encode NaN/Inf,
    which would otherwise turn a clean 422 into an unhandled 500.
    """
    if isinstance(obj, float) and not math.isfinite(obj):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=_sanitize_floats(jsonable_encoder(exc.errors())))


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(images.router)
app.include_router(regions.router)
app.include_router(jobs.router)
app.include_router(materials.router)
app.include_router(designs.router)
app.include_router(renders.router)
app.include_router(estimates.router)
app.include_router(reports.router)

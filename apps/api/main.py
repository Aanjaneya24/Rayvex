
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.api.logging_config import configure_logging
from apps.api.routers import auth, cases, escalations, evaluation, metrics, observability, policy, simulator, webhooks
from models.session import SessionLocal
from services.accounts.repository import ensure_default_accounts

logger = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates the DASHBOARD_CREDENTIALS accounts on first boot; no-op after that.
    session = SessionLocal()
    try:
        ensure_default_accounts(session)
        session.commit()
    finally:
        session.close()
    yield


app = FastAPI(title="Rayvex API", version="0.1.0", lifespan=lifespan)

cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "%s %s -> %s (%dms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response

app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(cases.router)
app.include_router(evaluation.router)
app.include_router(policy.router)
app.include_router(metrics.router)
app.include_router(escalations.router)
app.include_router(observability.router)
app.include_router(simulator.router)


@app.get("/health")
def health():
    return {"status": "ok"}

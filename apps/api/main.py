
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.api.logging_config import configure_logging
from apps.api.routers import cases, escalations, evaluation, metrics, observability, policy, simulator, webhooks

logger = configure_logging()

app = FastAPI(title="Rayvex API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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


import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.deps import get_db, get_redis
from models.benchmark_run import BenchmarkRun
from services.evaluation.benchmark import run_benchmark

router = APIRouter(prefix="/evaluation", tags=["evaluation"], dependencies=[Depends(get_current_user)])

ALLOWED_CASE_COUNTS = {100, 500, 1000, 5000, 10000}

_PROGRESS_KEY = "benchmark_progress:{run_token}"
_PROGRESS_TTL_SECONDS = 300


class RunBenchmarkRequest(BaseModel):
    case_count: int = Field(description="One of 100/500/1000/5000/10000")
    seed: int = 42
    run_token: str | None = None


def _serialize(run: BenchmarkRun) -> dict:
    return {
        "id": str(run.id), "seed": run.seed, "case_count": run.case_count,
        "naive_retry": run.naive_retry_metrics,
        "intelligent_recovery": run.intelligent_recovery_metrics,
        "unnecessary_actions_avoided": run.unnecessary_actions_avoided,
        "incremental_verified_revenue": str(run.incremental_verified_revenue),
        "created_at": run.created_at.isoformat(),
    }


@router.post("/benchmark")
def run_benchmark_endpoint(
    body: RunBenchmarkRequest, db: Session = Depends(get_db), redis_client=Depends(get_redis),
):
    if body.case_count not in ALLOWED_CASE_COUNTS:
        raise HTTPException(
            status_code=400, detail=f"case_count must be one of {sorted(ALLOWED_CASE_COUNTS)}"
        )

    on_progress = None
    if body.run_token:
        key = _PROGRESS_KEY.format(run_token=body.run_token)

        def on_progress(phase: str, processed: int, total: int) -> None:
            redis_client.set(
                key, json.dumps({"phase": phase, "processed": processed, "total": total}),
                ex=_PROGRESS_TTL_SECONDS,
            )

    run = run_benchmark(db, seed=body.seed, n=body.case_count, on_progress=on_progress)

    if body.run_token:
        redis_client.delete(_PROGRESS_KEY.format(run_token=body.run_token))

    return _serialize(run)


@router.get("/benchmark/progress/{run_token}")
def get_benchmark_progress(run_token: str, redis_client=Depends(get_redis)):
    raw = redis_client.get(_PROGRESS_KEY.format(run_token=run_token))
    if raw is None:
        return {"phase": None, "processed": None, "total": None}
    return json.loads(raw)


@router.get("/benchmark")
def list_benchmark_runs(db: Session = Depends(get_db), limit: int = 20):
    runs = db.query(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).limit(limit).all()
    return {"runs": [_serialize(r) for r in runs]}


@router.get("/benchmark/{run_id}")
def get_benchmark_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.get(BenchmarkRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="benchmark run not found")
    return _serialize(run)


import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from apps.api.deps import get_db, get_redis
from apps.api.rate_limit import check_rate_limit
from services.ingestion.queue import publish_case_event_standalone
from services.ingestion.webhook_processor import ingest_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay")
async def receive_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
):
    check_rate_limit(redis_client, request)

    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="RAZORPAY_WEBHOOK_SECRET is not configured; cannot verify webhook signatures.",
        )

    raw_body = await request.body()
    result = ingest_webhook(db, raw_body=raw_body, signature=x_razorpay_signature, secret=secret)

    if result.status == "invalid_signature":
        raise HTTPException(status_code=400, detail="invalid webhook signature")

    if result.status == "processed":
        # Commit explicitly before publishing: get_db's own commit doesn't
        # run until after this handler returns, and the worker could
        # otherwise pick the message up and query a case/event that isn't
        # durable yet. get_db's later commit becomes a no-op on an
        # already-clean session.
        db.commit()
        publish_case_event_standalone(
            case_id=result.case_id, correlation_id=result.correlation_id,
            reconciliation_needed=result.reconciliation_needed,
        )

    return {
        "status": result.status,
        "case_id": str(result.case_id) if result.case_id else None,
        "reconciliation_needed": result.reconciliation_needed,
    }

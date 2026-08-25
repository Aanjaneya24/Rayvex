
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.case import Case
from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, CaseType, EventType, ProcessingStatus
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.observability.pii_masking import mask_customer_id
from services.recovery.state_machine import RecoveryStateMachine

logger = logging.getLogger("rayvex.ingestion")

RAZORPAY_EVENT_TYPE_MAP = {
    "payment.failed": EventType.PAYMENT_FAILED,
    "payment.authorized": EventType.PAYMENT_AUTHORIZED,
    "payment.captured": EventType.PAYMENT_CAPTURED,
    "order.paid": EventType.ORDER_PAID,
}

RECONCILING_EVENT_TYPES = {EventType.PAYMENT_CAPTURED, EventType.ORDER_PAID}


def compute_signature(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = compute_signature(raw_body, secret)
    return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class IngestResult:
    status: str
    case_id: uuid.UUID | None
    correlation_id: uuid.UUID | None
    payment_event_id: uuid.UUID | None
    reconciliation_needed: bool
    untrusted_fields: dict


def _extract_entity(payload: dict, event_type_str: str) -> dict:
    if event_type_str == "order.paid":
        entity = payload["payload"]["order"]["entity"]
        return {
            "payment_id": None, "order_id": entity["id"],
            "amount": Decimal(entity["amount"]) / 100, "currency": entity["currency"],
            "method": None, "failure_code": None, "failure_reason": None,
            "notes": entity.get("notes", {}),
        }
    entity = payload["payload"]["payment"]["entity"]
    return {
        "payment_id": entity["id"], "order_id": entity.get("order_id"),
        "amount": Decimal(entity["amount"]) / 100, "currency": entity["currency"],
        "method": entity.get("method"), "failure_code": entity.get("error_code"),
        "failure_reason": entity.get("error_description"), "notes": entity.get("notes", {}),
    }


def _find_matching_case(session: Session, *, payment_id: str | None, order_id: str | None) -> Case | None:
    query = session.query(Case)
    if payment_id:
        case = query.filter(Case.payment_id == payment_id).order_by(Case.created_at.desc()).first()
        if case is not None:
            return case
    if order_id:
        return query.filter(Case.order_id == order_id).order_by(Case.created_at.desc()).first()
    return None


def ingest_webhook(session: Session, *, raw_body: bytes, signature: str, secret: str) -> IngestResult:
    is_valid = verify_signature(raw_body, signature, secret)
    payload = json.loads(raw_body)
    razorpay_event_id = payload["razorpay_event_id"]
    event_type_str = payload["event"]
    correlation_id = uuid.uuid4()

    raw_row = RawWebhookEvent(
        correlation_id=correlation_id, razorpay_event_id=razorpay_event_id, event_type=event_type_str,
        raw_payload=payload, signature_valid=is_valid, processing_status=ProcessingStatus.RECEIVED,
    )
    try:
        with session.begin_nested():
            session.add(raw_row)
            session.flush()
    except IntegrityError:
        return IngestResult(
            status="duplicate", case_id=None, correlation_id=None, payment_event_id=None,
            reconciliation_needed=False, untrusted_fields={},
        )

    if not is_valid:
        raw_row.processing_status = ProcessingStatus.FAILED
        session.flush()
        return IngestResult(
            status="invalid_signature", case_id=None, correlation_id=correlation_id, payment_event_id=None,
            reconciliation_needed=False, untrusted_fields={},
        )

    event_type = RAZORPAY_EVENT_TYPE_MAP.get(event_type_str)
    if event_type is None:
        raw_row.processing_status = ProcessingStatus.FAILED
        session.flush()
        return IngestResult(
            status="unrecognized_event_type", case_id=None, correlation_id=correlation_id,
            payment_event_id=None, reconciliation_needed=False, untrusted_fields={},
        )

    entity = _extract_entity(payload, event_type_str)
    notes = entity.pop("notes")

    case = _find_matching_case(session, payment_id=entity["payment_id"], order_id=entity["order_id"])
    sm = RecoveryStateMachine(session)
    reconciliation_needed = False

    customer_id = notes.get("rayvex_customer_id")
    if case is None:
        case = sm.create_case(
            correlation_id=correlation_id, case_type=CaseType.PAYMENT_FAILURE,
            merchant_id=notes.get("rayvex_merchant_id", "unknown_merchant"),
            customer_id=customer_id, payment_id=entity["payment_id"],
            order_id=entity["order_id"], amount=entity["amount"], currency=entity["currency"],
            payment_method=entity["method"], failure_code=entity["failure_code"],
            failure_reason=entity["failure_reason"], reason=f"{event_type_str} webhook received",
            actor="system:ingestion",
        )
        logger.info(
            "New case %s created from %s for customer=%s",
            case.id, event_type_str, mask_customer_id(customer_id),
        )
    elif case.current_state is CaseState.FAILED and event_type in RECONCILING_EVENT_TYPES:
        reconciliation_needed = True
        logger.info(
            "Reconciliation candidate: case %s customer=%s re-entering verification via %s",
            case.id, mask_customer_id(customer_id), event_type_str,
        )

    payment_event = PaymentEvent(
        event_id=razorpay_event_id, correlation_id=correlation_id, case_id=case.id,
        payment_id=entity["payment_id"], order_id=entity["order_id"], event_type=event_type,
        amount=entity["amount"], currency=entity["currency"], payment_method=entity["method"],
        failure_code=entity["failure_code"], failure_reason=entity["failure_reason"],
        timestamp=datetime.now(timezone.utc), raw_payload_reference=raw_row.id,
        received_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.PROCESSED,
    )
    session.add(payment_event)
    session.flush()

    raw_row.matched_case_id = case.id
    raw_row.processing_status = ProcessingStatus.PROCESSED
    session.flush()

    return IngestResult(
        status="processed", case_id=case.id, correlation_id=correlation_id,
        payment_event_id=payment_event.id, reconciliation_needed=reconciliation_needed,
        untrusted_fields=notes,
    )

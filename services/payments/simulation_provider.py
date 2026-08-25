
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.enums import EventType, ProviderMode
from models.payment_event import PaymentEvent
from services.payments.provider import OrderRecord, PaymentRecord, PaymentStatusResult, VerificationResult

_EVENT_TYPE_TO_STATUS = {
    EventType.PAYMENT_CAPTURED: "captured",
    EventType.PAYMENT_AUTHORIZED: "authorized",
    EventType.PAYMENT_FAILED: "failed",
    EventType.ORDER_PAID: "captured",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SimulationProvider:
    mode = ProviderMode.SIMULATION_MODE

    def __init__(self, session: Session):
        self._session = session

    def _latest_event_for_payment(self, payment_id: str) -> PaymentEvent | None:
        return self._session.execute(
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == payment_id)
            .order_by(PaymentEvent.timestamp.desc())
        ).scalars().first()

    def _latest_event_for_order(self, order_id: str) -> PaymentEvent | None:
        return self._session.execute(
            select(PaymentEvent)
            .where(PaymentEvent.order_id == order_id)
            .order_by(PaymentEvent.timestamp.desc())
        ).scalars().first()

    def _status_for(self, event: PaymentEvent | None) -> str:
        if event is None:
            return "created"
        return _EVENT_TYPE_TO_STATUS.get(event.event_type, "created")

    def get_payment(self, payment_id: str) -> PaymentRecord:
        event = self._latest_event_for_payment(payment_id)
        status = self._status_for(event)
        return PaymentRecord(
            mode=self.mode, payment_id=payment_id, order_id=event.order_id if event else None,
            amount=event.amount if event and event.amount is not None else Decimal("0"),
            currency=event.currency if event and event.currency else "INR", status=status,
            method=event.payment_method if event else None,
            error_code=event.failure_code if event else None,
            error_description=event.failure_reason if event else None,
            raw_response={
                "simulated_from_event_id": str(event.id) if event else None,
                "event_type": event.event_type.value if event else None,
            },
            fetched_at=_now(),
        )

    def get_order(self, order_id: str) -> OrderRecord:
        event = self._latest_event_for_order(order_id)
        status = "paid" if event and event.event_type in (EventType.PAYMENT_CAPTURED, EventType.ORDER_PAID) else "attempted"
        if event is None:
            status = "created"
        return OrderRecord(
            mode=self.mode, order_id=order_id,
            amount=event.amount if event and event.amount is not None else Decimal("0"),
            currency=event.currency if event and event.currency else "INR", status=status,
            raw_response={"simulated_from_event_id": str(event.id) if event else None},
            fetched_at=_now(),
        )

    def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        event = self._latest_event_for_payment(payment_id)
        return PaymentStatusResult(
            mode=self.mode, payment_id=payment_id, status=self._status_for(event), fetched_at=_now(),
        )

    def verify_payment(self, payment_id: str) -> VerificationResult:
        event = self._latest_event_for_payment(payment_id)
        status = self._status_for(event)
        return VerificationResult(
            mode=self.mode, payment_id=payment_id, status=status,
            amount=event.amount if event else None, currency=event.currency if event else None,
            raw_response={
                "simulated_from_event_id": str(event.id) if event else None,
                "event_type": event.event_type.value if event else None,
                "note": "SIMULATION MODE: derived from Rayvex's own persisted PaymentEvent "
                        "history, not a real Razorpay API call.",
            },
            fetched_at=_now(),
        )


import os
from datetime import datetime, timezone
from decimal import Decimal

import razorpay

from models.enums import ProviderMode
from services.payments.provider import OrderRecord, PaymentRecord, PaymentStatusResult, VerificationResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RazorpayProvider:
    mode = ProviderMode.RAZORPAY_TEST_MODE

    def __init__(self, client: razorpay.Client | None = None):
        if client is not None:
            self._client = client
        else:
            key_id = os.environ.get("RAZORPAY_KEY_ID")
            key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
            if not key_id or not key_secret:
                raise RuntimeError(
                    "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must both be set to use "
                    "RazorpayProvider. Copy .env.example and fill them in with real Test "
                    "Mode credentials, or use SimulationProvider instead; never fake "
                    "credentials to bypass this."
                )
            self._client = razorpay.Client(auth=(key_id, key_secret))

    def get_payment(self, payment_id: str) -> PaymentRecord:
        raw = self._client.payment.fetch(payment_id)
        return PaymentRecord(
            mode=self.mode, payment_id=raw["id"], order_id=raw.get("order_id"),
            amount=Decimal(raw["amount"]) / 100, currency=raw["currency"], status=raw["status"],
            method=raw.get("method"), error_code=raw.get("error_code"),
            error_description=raw.get("error_description"), raw_response=raw, fetched_at=_now(),
        )

    def get_order(self, order_id: str) -> OrderRecord:
        raw = self._client.order.fetch(order_id)
        return OrderRecord(
            mode=self.mode, order_id=raw["id"], amount=Decimal(raw["amount"]) / 100,
            currency=raw["currency"], status=raw["status"], raw_response=raw, fetched_at=_now(),
        )

    def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        raw = self._client.payment.fetch(payment_id)
        return PaymentStatusResult(
            mode=self.mode, payment_id=raw["id"], status=raw["status"], fetched_at=_now(),
        )

    def verify_payment(self, payment_id: str) -> VerificationResult:
        raw = self._client.payment.fetch(payment_id)
        return VerificationResult(
            mode=self.mode, payment_id=raw["id"], status=raw["status"],
            amount=Decimal(raw["amount"]) / 100 if "amount" in raw else None,
            currency=raw.get("currency"), raw_response=raw, fetched_at=_now(),
        )

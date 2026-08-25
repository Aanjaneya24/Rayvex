
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from models.enums import ProviderMode


@dataclass(frozen=True)
class PaymentRecord:
    mode: ProviderMode
    payment_id: str
    order_id: str | None
    amount: Decimal
    currency: str
    status: str
    method: str | None
    error_code: str | None
    error_description: str | None
    raw_response: dict
    fetched_at: datetime


@dataclass(frozen=True)
class OrderRecord:
    mode: ProviderMode
    order_id: str
    amount: Decimal
    currency: str
    status: str
    raw_response: dict
    fetched_at: datetime


@dataclass(frozen=True)
class PaymentStatusResult:
    mode: ProviderMode
    payment_id: str
    status: str
    fetched_at: datetime


@dataclass(frozen=True)
class VerificationResult:

    mode: ProviderMode
    payment_id: str
    status: str
    amount: Decimal | None
    currency: str | None
    raw_response: dict
    fetched_at: datetime


class PaymentProvider(Protocol):
    def get_payment(self, payment_id: str) -> PaymentRecord: ...

    def get_order(self, order_id: str) -> OrderRecord: ...

    def get_payment_status(self, payment_id: str) -> PaymentStatusResult: ...

    def verify_payment(self, payment_id: str) -> VerificationResult: ...

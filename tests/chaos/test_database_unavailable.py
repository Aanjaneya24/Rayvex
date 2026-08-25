
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from models.enums import CaseType
from models.session import make_engine
from services.recovery.state_machine import RecoveryStateMachine


@pytest.fixture()
def unreachable_session():
    broken_engine = make_engine("postgresql+psycopg://rayvex:rayvex@localhost:1/rayvex?connect_timeout=2")
    Session = sessionmaker(bind=broken_engine, future=True)
    session = Session()
    yield session
    session.close()
    broken_engine.dispose()


def test_case_creation_raises_rather_than_silently_no_oping(unreachable_session):
    sm = RecoveryStateMachine(unreachable_session)
    with pytest.raises(OperationalError):
        sm.create_case(
            correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_1",
            customer_id="cust_1", payment_id="pay_1", order_id="order_1", amount=Decimal("1000.00"),
            currency="INR", payment_method="upi", failure_code="bank_timeout",
            failure_reason="payment_failed", reason="payment.failed webhook received",
            actor="system:ingestion",
        )


def test_verification_run_raises_rather_than_reporting_a_fabricated_outcome(unreachable_session):
    from services.payments.verification import run_verification

    class UnreachableProvider:
        mode = None

        def verify_payment(self, payment_id: str):
            raise AssertionError("should never be called — the DB read before this fails first")

    with pytest.raises(OperationalError):
        run_verification(
            unreachable_session, UnreachableProvider(), case_id=uuid.uuid4(), correlation_id=uuid.uuid4(),
        )


import inspect
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.payments.provider import (
    OrderRecord,
    PaymentRecord,
    PaymentStatusResult,
    ProviderMode,
    VerificationResult,
)


@pytest.mark.parametrize("result_class", [PaymentRecord, OrderRecord, PaymentStatusResult, VerificationResult])
def test_mode_has_no_default_and_is_the_first_field(result_class):
    fields = list(inspect.signature(result_class).parameters.values())
    assert fields[0].name == "mode"
    assert fields[0].default is inspect.Parameter.empty


def test_constructing_payment_record_without_mode_raises():
    with pytest.raises(TypeError):
        PaymentRecord(
            payment_id="pay_1", order_id=None, amount=Decimal("100"), currency="INR",
            status="captured", method="upi", error_code=None, error_description=None,
            raw_response={}, fetched_at=datetime.now(timezone.utc),
        )


def test_both_provider_mode_values_are_distinct_and_real():
    assert ProviderMode.RAZORPAY_TEST_MODE.value == "RAZORPAY_TEST_MODE"
    assert ProviderMode.SIMULATION_MODE.value == "SIMULATION_MODE"
    assert ProviderMode.RAZORPAY_TEST_MODE != ProviderMode.SIMULATION_MODE

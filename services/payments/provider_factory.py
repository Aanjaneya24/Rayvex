
import os

from sqlalchemy.orm import Session

from services.payments.provider import PaymentProvider
from services.payments.razorpay_provider import RazorpayProvider
from services.payments.simulation_provider import SimulationProvider


def build_default_payment_provider(session: Session) -> PaymentProvider:
    if os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"):
        return RazorpayProvider()
    return SimulationProvider(session)

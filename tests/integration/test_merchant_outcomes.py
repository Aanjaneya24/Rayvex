
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.enums import CaseState, CaseType, RecoveryAction
from models.merchant_recovery_outcome import MerchantRecoveryOutcome
from services.payments.provider import ProviderMode, VerificationResult
from services.payments.verification import run_verification
from services.recovery.expected_value import RecoveryConfigSnapshot
from services.recovery.probability import EmpiricalRecoveryProbabilityEstimator, RecoveryCaseContext
from services.recovery.state_machine import RecoveryStateMachine


class FixedResultProvider:
    def __init__(self, result: VerificationResult):
        self.mode = result.mode
        self._result = result

    def verify_payment(self, payment_id: str) -> VerificationResult:
        return self._result


def drive_case_to_verification_pending(sm: RecoveryStateMachine, *, action=RecoveryAction.RETRY, payment_id="pay_1"):
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_real_1",
        customer_id="cust_1", payment_id=payment_id, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION, CaseState.ACTION_PENDING,
    ]:
        sm.transition(case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
                       correlation_id=uuid.uuid4())
    sm.transition(
        case.id, to_state=CaseState.ACTION_EXECUTED, reason=f"{action.value} executed (simulated)",
        actor="system:simulated_action_executor", correlation_id=uuid.uuid4(),
        evidence={"action": action.value, "simulated": True},
    )
    sm.transition(case.id, to_state=CaseState.VERIFICATION_PENDING, reason="advancing",
                   actor="system:pipeline", correlation_id=uuid.uuid4())
    return case


def make_config(**overrides) -> RecoveryConfigSnapshot:
    defaults = dict(
        id=None, version=1, merchant_id=None,
        default_probability_by_action={a: 0.13 for a in RecoveryAction},
        action_cost_by_action={a: Decimal("1.00") for a in RecoveryAction},
        risk_cost_multiplier=0.05, min_sample_size=2,
        smoothing_alpha=1.0, smoothing_beta=1.0,
    )
    defaults.update(overrides)
    return RecoveryConfigSnapshot(**defaults)


def test_recovered_verification_records_merchant_outcome(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm, action=RecoveryAction.RETRY)
    provider = FixedResultProvider(VerificationResult(
        mode=ProviderMode.SIMULATION_MODE, payment_id=case.payment_id, status="captured",
        amount=case.amount, currency="INR", raw_response={}, fetched_at=datetime.now(timezone.utc),
    ))

    run_verification(db_session, provider, case_id=case.id, correlation_id=uuid.uuid4())

    rows = db_session.query(MerchantRecoveryOutcome).filter_by(case_id=case.id).all()
    assert len(rows) == 1
    assert rows[0].merchant_id == "merchant_real_1"
    assert rows[0].action_taken == RecoveryAction.RETRY
    assert rows[0].recovered is True


def test_failed_verification_records_merchant_outcome_as_not_recovered(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm, action=RecoveryAction.RETRY, payment_id="pay_2")
    provider = FixedResultProvider(VerificationResult(
        mode=ProviderMode.SIMULATION_MODE, payment_id=case.payment_id, status="failed",
        amount=case.amount, currency="INR", raw_response={}, fetched_at=datetime.now(timezone.utc),
    ))

    run_verification(db_session, provider, case_id=case.id, correlation_id=uuid.uuid4())

    rows = db_session.query(MerchantRecoveryOutcome).filter_by(case_id=case.id).all()
    assert len(rows) == 1
    assert rows[0].recovered is False


def test_still_pending_verification_records_no_outcome(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm, action=RecoveryAction.RETRY, payment_id="pay_3")
    provider = FixedResultProvider(VerificationResult(
        mode=ProviderMode.SIMULATION_MODE, payment_id=case.payment_id, status="authorized",
        amount=case.amount, currency="INR", raw_response={}, fetched_at=datetime.now(timezone.utc),
    ))

    run_verification(db_session, provider, case_id=case.id, correlation_id=uuid.uuid4())

    rows = db_session.query(MerchantRecoveryOutcome).filter_by(case_id=case.id).all()
    assert rows == []


def test_probability_estimator_uses_real_merchant_outcomes(db_session):
    sm = RecoveryStateMachine(db_session)
    for i in range(3):
        case = drive_case_to_verification_pending(sm, action=RecoveryAction.RETRY, payment_id=f"pay_real_{i}")
        provider = FixedResultProvider(VerificationResult(
            mode=ProviderMode.SIMULATION_MODE, payment_id=case.payment_id, status="captured",
            amount=case.amount, currency="INR", raw_response={}, fetched_at=datetime.now(timezone.utc),
        ))
        run_verification(db_session, provider, case_id=case.id, correlation_id=uuid.uuid4())

    estimator = EmpiricalRecoveryProbabilityEstimator()
    context = RecoveryCaseContext(
        merchant_id="merchant_real_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    estimate = estimator.estimate(
        db_session, context=context, action=RecoveryAction.RETRY, config=make_config(min_sample_size=3),
    )

    assert estimate.source_tier == "merchant_specific"
    assert estimate.real_sample_size == 3
    assert estimate.sample_size == 3


def test_record_merchant_outcome_skips_when_no_action_execution_exists(db_session):
    from services.recovery.merchant_outcomes import record_merchant_outcome

    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_no_action",
        customer_id="cust_1", payment_id="pay_no_action", order_id="order_1", amount=Decimal("500.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )

    result = record_merchant_outcome(db_session, case, recovered=True)

    assert result is None
    rows = db_session.query(MerchantRecoveryOutcome).filter_by(case_id=case.id).all()
    assert rows == []

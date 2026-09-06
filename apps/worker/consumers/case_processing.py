
import uuid

import redis
from sqlalchemy.orm import Session

from models.enums import CaseState
from services.payments.provider import PaymentProvider
from services.payments.provider_factory import build_default_payment_provider
from services.payments.reconciliation import reconcile_and_reverify
from services.policy.config_repository import get_active_config
from services.recovery.case_orchestrator import CasePipelineResult, ScriptedDecision, run_case_pipeline
from services.recovery.state_machine import RecoveryStateMachine
from services.risk.risk_scoring import check_risk as compute_risk_assessment


def process_case_event(
    session: Session,
    redis_client: redis.Redis,
    *,
    case_id: uuid.UUID,
    correlation_id: uuid.UUID,
    reconciliation_needed: bool,
    provider: PaymentProvider | None = None,
    llm=None,
    scripted_decision: ScriptedDecision | None = None,
) -> CasePipelineResult | None:
    """The heavy processing done off the webhook request path: advancing
    a newly-received case through the full recovery pipeline, or
    reconciling one that had already reached FAILED. Called
    once per `case_processing` queue message, with its own session/redis
    client (a fresh one per message in the real worker; the caller's
    fixtures directly in tests).

    Idempotent against a case that already moved past the state this
    message expected: a second event for a case already mid-pipeline (or
    a redelivered message) is a no-op rather than an error, since another
    message may have already advanced it.
    """
    sm = RecoveryStateMachine(session)
    case = sm.get_case(case_id)
    provider = provider if provider is not None else build_default_payment_provider(session)

    if reconciliation_needed:
        if case.current_state is not CaseState.FAILED:
            return None
        verification_result = reconcile_and_reverify(
            session, provider, case_id=case_id, correlation_id=correlation_id,
            reason="a later payment.captured/order.paid event arrived after an earlier failure, reconciling",
        )
        return CasePipelineResult(
            case=sm.get_case(case_id), decision=None, gate_result=None,
            verification_result=verification_result,
        )

    if case.current_state is not CaseState.RECEIVED:
        return None

    config = get_active_config(session, case.merchant_id)
    risk = compute_risk_assessment(
        session, redis_client, case_id=case.id, customer_id=case.customer_id or "",
        velocity_window_seconds=config.suspicious_velocity_window_seconds,
        velocity_threshold=config.suspicious_velocity_threshold,
    )
    return run_case_pipeline(
        session, redis_client, case_id=case_id, correlation_id=correlation_id,
        risk_score=risk.risk_score, provider=provider, llm=llm, scripted_decision=scripted_decision,
    )

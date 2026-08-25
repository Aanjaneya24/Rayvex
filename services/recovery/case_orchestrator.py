
import uuid
from dataclasses import dataclass

import redis
from sqlalchemy.orm import Session

from models.agent_decision import AgentDecision
from models.case import Case
from models.enums import CaseState, RecoveryAction
from services.agent.orchestrator import RecoveryAgentOrchestrator
from services.agent.schema import SCHEMA_VERSION, AgentDecisionOutput
from services.payments.provider import PaymentProvider
from services.payments.provider_factory import build_default_payment_provider
from services.payments.verification import VerificationRunResult, run_verification
from services.policy.config_repository import get_active_config
from services.policy.engine import evaluate
from services.recovery.action_gate import ActionGateResult, check_action_before_execution
from services.recovery.policy_context_builder import build_policy_context
from services.recovery.state_machine import RecoveryStateMachine
from services.risk.risk_scoring import risk_level_for

_DETERMINISTIC_STOP_RULE_IDS = frozenset({
    "suspicious_velocity_stop_and_escalate", "max_retry_count_exceeded",
})

DETERMINISTIC_SKIP_MODEL_BACKEND = "skipped:deterministic_policy"


@dataclass(frozen=True)
class ScriptedDecision:

    action: RecoveryAction
    reason: str
    confidence: float
    expected_recovery_value: float
    risk_level: str


@dataclass(frozen=True)
class CasePipelineResult:
    case: Case
    decision: AgentDecisionOutput | None
    gate_result: ActionGateResult | None
    verification_result: VerificationRunResult | None


def advance_to_decision(sm: RecoveryStateMachine, *, case_id: uuid.UUID, correlation_id: uuid.UUID) -> Case:
    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK, CaseState.DECISION,
    ]:
        sm.transition(
            case_id, to_state=to_state, reason=f"advancing to {to_state.value}",
            actor="system:pipeline", correlation_id=correlation_id,
        )
    return sm.get_case(case_id)


def check_deterministic_stop(
    session: Session, redis_client: redis.Redis, *, case: Case, risk_score: float,
    current_hour: int | None = None,
) -> str | None:
    config = get_active_config(session, case.merchant_id)
    context = build_policy_context(
        session, redis_client, case, RecoveryAction.STOP, config,
        risk_score=risk_score, current_hour=current_hour,
    )
    verdict = evaluate(context, config)
    if verdict.rule_id in _DETERMINISTIC_STOP_RULE_IDS:
        return verdict.reason
    return None


def _record_skipped_decision(
    session: Session, *, case_id: uuid.UUID, correlation_id: uuid.UUID, reason: str, risk_score: float,
) -> AgentDecisionOutput:
    decision = AgentDecisionOutput(
        action=RecoveryAction.STOP, reason=reason, confidence=1.0,
        expected_recovery_value=0.0, risk_level=risk_level_for(risk_score),
    )
    session.add(AgentDecision(
        case_id=case_id, correlation_id=correlation_id, proposed_action=decision.action,
        reason=decision.reason, confidence=decision.confidence,
        expected_recovery_value=decision.expected_recovery_value, risk_level=decision.risk_level,
        model_backend=DETERMINISTIC_SKIP_MODEL_BACKEND, model_name=DETERMINISTIC_SKIP_MODEL_BACKEND,
        prompt_version="n/a", schema_version=SCHEMA_VERSION, tool_trace=[],
        llm_call_count=0, total_latency_ms=0, estimated_cost_usd=0.0,
    ))
    session.flush()
    return decision


def get_agent_decision(
    session: Session, redis_client: redis.Redis, *, case_id: uuid.UUID, correlation_id: uuid.UUID,
    llm=None, scripted_decision: ScriptedDecision | None = None, untrusted_fields: dict | None = None,
) -> tuple[AgentDecisionOutput, str]:
    if scripted_decision is not None:
        from models.agent_decision import AgentDecision
        from services.agent.schema import SCHEMA_VERSION
        from services.agent.validation import parse_agent_decision

        decision = parse_agent_decision({
            "action": scripted_decision.action.value, "reason": scripted_decision.reason,
            "confidence": scripted_decision.confidence,
            "expected_recovery_value": scripted_decision.expected_recovery_value,
            "risk_level": scripted_decision.risk_level,
        })
        model_backend = "scripted:no-llm-configured"
        session.add(AgentDecision(
            case_id=case_id, correlation_id=correlation_id, proposed_action=decision.action,
            reason=decision.reason, confidence=decision.confidence,
            expected_recovery_value=decision.expected_recovery_value, risk_level=decision.risk_level,
            model_backend=model_backend, model_name=model_backend, prompt_version="n/a",
            schema_version=SCHEMA_VERSION, tool_trace=[],
        ))
        session.flush()
        return decision, model_backend

    from services.agent.orchestrator import build_llm

    resolved_llm = llm if llm is not None else build_llm()
    orchestrator = RecoveryAgentOrchestrator(llm=resolved_llm)
    decision = orchestrator.propose(
        session, redis_client, case_id=case_id, correlation_id=correlation_id,
        untrusted_fields=untrusted_fields,
    )
    return decision, type(resolved_llm).__name__


def execute_and_verify(
    session: Session, provider: PaymentProvider, *, case_id: uuid.UUID, action: RecoveryAction,
    correlation_id: uuid.UUID,
) -> VerificationRunResult:
    sm = RecoveryStateMachine(session)
    sm.transition(
        case_id, to_state=CaseState.ACTION_EXECUTED, reason=f"{action.value} executed (simulated — no Action Executor exists yet)",
        actor="system:simulated_action_executor", correlation_id=correlation_id,
        evidence={"action": action.value, "simulated": True},
    )
    sm.transition(
        case_id, to_state=CaseState.VERIFICATION_PENDING, reason="awaiting payment status confirmation",
        actor="system:pipeline", correlation_id=correlation_id,
    )
    return run_verification(session, provider, case_id=case_id, correlation_id=correlation_id)


def run_case_pipeline(
    session: Session, redis_client: redis.Redis, *, case_id: uuid.UUID, correlation_id: uuid.UUID,
    llm=None, scripted_decision: ScriptedDecision | None = None, provider: PaymentProvider | None = None,
    risk_score: float = 0.1, untrusted_fields: dict | None = None, current_hour: int | None = None,
) -> CasePipelineResult:
    sm = RecoveryStateMachine(session)
    provider = provider if provider is not None else build_default_payment_provider(session)

    advance_to_decision(sm, case_id=case_id, correlation_id=correlation_id)

    case = sm.get_case(case_id)
    deterministic_stop_reason = check_deterministic_stop(
        session, redis_client, case=case, risk_score=risk_score, current_hour=current_hour,
    )
    if deterministic_stop_reason is not None:
        decision = _record_skipped_decision(
            session, case_id=case_id, correlation_id=correlation_id,
            reason=deterministic_stop_reason, risk_score=risk_score,
        )
        model_backend = DETERMINISTIC_SKIP_MODEL_BACKEND
    else:
        decision, model_backend = get_agent_decision(
            session, redis_client, case_id=case_id, correlation_id=correlation_id, llm=llm,
            scripted_decision=scripted_decision, untrusted_fields=untrusted_fields,
        )

    sm.transition(
        case_id, to_state=CaseState.ACTION_PENDING, reason=f"{decision.action.value} proposed: {decision.reason}",
        actor=f"agent:{model_backend}", correlation_id=correlation_id,
    )

    gate_result = check_action_before_execution(
        session, redis_client, case_id=case_id, proposed_action=decision.action,
        correlation_id=correlation_id, risk_score=risk_score, current_hour=current_hour,
    )

    if not gate_result.approved:
        return CasePipelineResult(
            case=sm.get_case(case_id), decision=decision, gate_result=gate_result, verification_result=None,
        )

    verification_result = execute_and_verify(
        session, provider, case_id=case_id, action=decision.action, correlation_id=correlation_id,
    )
    return CasePipelineResult(
        case=sm.get_case(case_id), decision=decision, gate_result=gate_result,
        verification_result=verification_result,
    )

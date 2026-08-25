
import uuid
from dataclasses import dataclass

import redis
from sqlalchemy.orm import Session

from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, PolicyVerdictType, RecoveryAction
from models.policy_decision import PolicyDecision
from services.policy.config_repository import get_active_config
from services.policy.decisions import persist_policy_decision
from services.policy.engine import evaluate
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.policy_context_builder import build_policy_context
from services.recovery.state_machine import RecoveryStateMachine


@dataclass(frozen=True)
class ActionGateResult:
    approved: bool
    resulting_action: RecoveryAction | None
    policy_decision: PolicyDecision
    transition: CaseStateTransition | None


def check_action_before_execution(
    session: Session,
    redis_client: redis.Redis,
    *,
    case_id: uuid.UUID,
    proposed_action: RecoveryAction,
    correlation_id: uuid.UUID,
    risk_score: float,
    current_hour: int | None = None,
) -> ActionGateResult:
    sm = RecoveryStateMachine(session)
    case = sm.get_case(case_id)
    if case.current_state is not CaseState.ACTION_PENDING:
        raise WrongCaseStateError(case_id, CaseState.ACTION_PENDING, case.current_state)

    config = get_active_config(session, case.merchant_id)
    context = build_policy_context(
        session, redis_client, case, proposed_action, config, risk_score=risk_score,
        current_hour=current_hour,
    )
    verdict = evaluate(context, config)

    decision_row = persist_policy_decision(
        session,
        case=case,
        config=config,
        context=context,
        verdict=verdict,
        correlation_id=correlation_id,
    )

    if verdict.verdict_type is PolicyVerdictType.ALLOW:
        return ActionGateResult(
            approved=True,
            resulting_action=verdict.resulting_action,
            policy_decision=decision_row,
            transition=None,
        )

    transition = sm.transition(
        case.id,
        to_state=CaseState.STOPPED,
        reason=verdict.reason,
        actor="system:policy_engine",
        correlation_id=correlation_id,
        evidence={
            "policy_decision_id": str(decision_row.id),
            "rule_id": verdict.rule_id,
            "proposed_action": proposed_action.value,
            "requires_escalation": verdict.requires_escalation,
        },
        policy_decision_id=decision_row.id,
    )
    return ActionGateResult(
        approved=False,
        resulting_action=verdict.resulting_action,
        policy_decision=decision_row,
        transition=transition,
    )

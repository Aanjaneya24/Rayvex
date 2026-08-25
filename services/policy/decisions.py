
import uuid
from dataclasses import asdict
from decimal import Decimal

from sqlalchemy.orm import Session

from models.case import Case
from models.policy_decision import PolicyDecision
from services.policy.context import PolicyConfigSnapshot, PolicyContext, PolicyVerdict


def _json_safe_context(context: PolicyContext) -> dict:
    raw = asdict(context)
    raw["amount"] = str(context.amount) if isinstance(context.amount, Decimal) else raw["amount"]
    raw["proposed_action"] = context.proposed_action.value
    return raw


def persist_policy_decision(
    session: Session,
    *,
    case: Case,
    config: PolicyConfigSnapshot,
    context: PolicyContext,
    verdict: PolicyVerdict,
    correlation_id: uuid.UUID,
) -> PolicyDecision:
    row = PolicyDecision(
        case_id=case.id,
        correlation_id=correlation_id,
        policy_config_id=config.id,
        policy_config_version=config.version,
        proposed_action=context.proposed_action,
        verdict_type=verdict.verdict_type,
        resulting_action=verdict.resulting_action,
        rule_id=verdict.rule_id,
        reason=verdict.reason,
        requires_escalation=verdict.requires_escalation,
        context_snapshot=_json_safe_context(context),
    )
    session.add(row)
    session.flush()
    return row

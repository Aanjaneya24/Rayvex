
from decimal import Decimal

import redis
from langchain_core.tools import StructuredTool, tool
from sqlalchemy.orm import Session

from models.case import Case
from models.enums import RecoveryAction
from services.agent.tools._util import parse_uuid_or_none
from services.policy.config_repository import get_active_config
from services.policy.engine import evaluate
from services.recovery.expected_value import (
    calculate_expected_risk_cost,
    calculate_expected_value,
    evaluate_candidate_actions,
)
from services.recovery.policy_context_builder import build_policy_context
from services.recovery.probability import RecoveryCaseContext
from services.recovery.probability_factory import build_probability_estimator
from services.recovery.recovery_config_repository import get_active_recovery_config
from services.risk.risk_scoring import check_risk as compute_risk_assessment

CANDIDATE_INTERVENTIONAL_ACTIONS = [
    RecoveryAction.RETRY,
    RecoveryAction.SEND_RECOVERY_REMINDER,
    RecoveryAction.SEND_RECOVERY_LINK,
    RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
]


def build_reasoning_tools(session: Session, redis_client: redis.Redis) -> list[StructuredTool]:
    estimator = build_probability_estimator()

    def _load_case(case_id: str) -> Case | None:
        parsed = parse_uuid_or_none(case_id)
        return session.get(Case, parsed) if parsed else None

    def predict_recovery_probability(case_id: str, action: str) -> dict:
        """Estimate the probability that this action recovers this case."""
        case = _load_case(case_id)
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        recovery_config = get_active_recovery_config(session, case.merchant_id)
        context = RecoveryCaseContext(
            merchant_id=case.merchant_id, failure_code=case.failure_code or "",
            payment_method=case.payment_method or "", amount=case.amount,
        )
        estimate = estimator.estimate(
            session, context=context, action=RecoveryAction(action), config=recovery_config,
        )
        return {
            "probability": estimate.probability, "source_tier": estimate.source_tier,
            "sample_size": estimate.sample_size,
            "real_sample_size": estimate.real_sample_size,
        }

    def calculate_expected_value_tool(
        case_id: str, action: str, probability: float, risk_score: float,
    ) -> dict:
        """Calculate the expected recovery value of an action given its probability and risk."""
        case = _load_case(case_id)
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        recovery_config = get_active_recovery_config(session, case.merchant_id)
        recovery_action = RecoveryAction(action)
        action_cost = recovery_config.action_cost_by_action[recovery_action]
        expected_risk_cost = calculate_expected_risk_cost(
            risk_score=risk_score, amount=case.amount,
            risk_cost_multiplier=recovery_config.risk_cost_multiplier,
        )
        ev = calculate_expected_value(
            probability=probability, recoverable_amount=case.amount,
            action_cost=action_cost, expected_risk_cost=expected_risk_cost,
        )
        return {
            "expected_recovery_value": float(ev), "action_cost": float(action_cost),
            "expected_risk_cost": float(expected_risk_cost),
        }

    def check_risk(case_id: str) -> dict:
        """Compute this case's risk score, level, and velocity signals."""
        case = _load_case(case_id)
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        config = get_active_config(session, case.merchant_id)
        assessment = compute_risk_assessment(
            session, redis_client, case_id=case.id, customer_id=case.customer_id or "",
            velocity_window_seconds=config.suspicious_velocity_window_seconds,
            velocity_threshold=config.suspicious_velocity_threshold,
        )
        return {
            "risk_score": assessment.risk_score, "risk_level": assessment.risk_level.value,
            "suspicious_velocity": assessment.suspicious_velocity,
            "retry_count": assessment.retry_count,
        }

    def check_policy(case_id: str, action: str, risk_score: float) -> dict:
        """Preview how the policy engine would rule on this action (not binding)."""
        case = _load_case(case_id)
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        config = get_active_config(session, case.merchant_id)
        context = build_policy_context(
            session, redis_client, case, RecoveryAction(action), config, risk_score=risk_score,
        )
        verdict = evaluate(context, config)
        return {
            "verdict_type": verdict.verdict_type.value,
            "resulting_action": verdict.resulting_action.value if verdict.resulting_action else None,
            "rule_id": verdict.rule_id, "reason": verdict.reason,
            "requires_escalation": verdict.requires_escalation,
            "note": "PREVIEW ONLY, not persisted, not binding. Real enforcement happens later.",
        }

    def choose_recovery_action(case_id: str, risk_score: float) -> dict:
        """Rank candidate recovery actions for this case by expected value."""
        case = _load_case(case_id)
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        recovery_config = get_active_recovery_config(session, case.merchant_id)
        context = RecoveryCaseContext(
            merchant_id=case.merchant_id, failure_code=case.failure_code or "",
            payment_method=case.payment_method or "", amount=case.amount,
        )
        evaluations = evaluate_candidate_actions(
            session, estimator, context=context, candidate_actions=CANDIDATE_INTERVENTIONAL_ACTIONS,
            risk_score=risk_score, config=recovery_config,
        )
        return {
            "ranking": [
                {
                    "action": e.action.value,
                    "probability": e.probability_estimate.probability,
                    "source_tier": e.probability_estimate.source_tier,
                    "expected_recovery_value": float(e.expected_recovery_value),
                }
                for e in evaluations
            ]
        }

    return [
        tool(predict_recovery_probability),
        StructuredTool.from_function(calculate_expected_value_tool, name="calculate_expected_value"),
        tool(check_risk),
        tool(check_policy),
        tool(choose_recovery_action),
    ]

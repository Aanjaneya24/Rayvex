
import uuid

from langchain_core.tools import StructuredTool, tool
from sqlalchemy.orm import Session

from models.agent_decision import AgentDecision
from services.agent.schema import AgentDecisionOutput


def _propose(action_name: str, case_id: str, reason: str) -> dict:
    return {
        "status": "PROPOSED_NOT_EXECUTED",
        "action": action_name,
        "case_id": case_id,
        "note": (
            f"{action_name} has been noted as a candidate action with reason "
            f"'{reason}'. It has NOT been executed and no payment/case state has "
            f"changed. Execution requires policy approval "
            f"(services/recovery/action_gate.py) and is carried out by the Action "
            f"Executor, never by this tool."
        ),
    }


def retry_payment(case_id: str, reason: str) -> dict:
    """Propose retrying the payment. Does not execute anything."""
    return _propose("RETRY", case_id, reason)


def send_recovery_reminder(case_id: str, reason: str) -> dict:
    """Propose sending a recovery reminder. Does not execute anything."""
    return _propose("SEND_RECOVERY_REMINDER", case_id, reason)


def send_recovery_link(case_id: str, reason: str) -> dict:
    """Propose sending a recovery link. Does not execute anything."""
    return _propose("SEND_RECOVERY_LINK", case_id, reason)


def suggest_alternative_payment(case_id: str, reason: str) -> dict:
    """Propose suggesting an alternative payment method. Does not execute anything."""
    return _propose("SUGGEST_ALTERNATIVE_PAYMENT_METHOD", case_id, reason)


def escalate_case(case_id: str, reason: str) -> dict:
    """Propose escalating the case to a human reviewer. Does not execute anything."""
    return _propose("ESCALATE_TO_HUMAN", case_id, reason)


def build_action_proposal_tools() -> list[StructuredTool]:
    return [
        tool(retry_payment),
        tool(send_recovery_reminder),
        tool(send_recovery_link),
        tool(suggest_alternative_payment),
        tool(escalate_case),
    ]


def build_record_decision_tool(
    session: Session, *, case_id: uuid.UUID, correlation_id: uuid.UUID, model_backend: str,
    model_name: str, prompt_version: str, schema_version: str, tool_trace: list[dict],
    usage_stats: dict | None = None,
) -> StructuredTool:

    def record_decision(decision_json: str) -> dict:
        """Validate and persist the final structured decision. Call this last."""
        from services.agent.validation import parse_agent_decision

        decision = parse_agent_decision(decision_json)
        stats = usage_stats or {}
        row = AgentDecision(
            case_id=case_id, correlation_id=correlation_id, proposed_action=decision.action,
            reason=decision.reason, confidence=decision.confidence,
            expected_recovery_value=decision.expected_recovery_value,
            risk_level=decision.risk_level, model_backend=model_backend, model_name=model_name,
            prompt_version=prompt_version, schema_version=schema_version, tool_trace=tool_trace,
            llm_call_count=stats.get("llm_call_count", 0),
            total_latency_ms=stats.get("total_latency_ms", 0),
            estimated_cost_usd=stats.get("estimated_cost_usd", 0.0),
        )
        session.add(row)
        session.flush()
        return {"recorded": True, "agent_decision_id": str(row.id)}

    return StructuredTool.from_function(record_decision, name="record_decision")

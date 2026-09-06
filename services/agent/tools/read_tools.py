
from langchain_core.tools import StructuredTool, tool
from sqlalchemy.orm import Session

from models.case import Case
from services.agent.tools._util import parse_uuid_or_none
from services.evaluation.outcomes_repository import global_baseline_stats, segment_stats
from services.payments.provider import PaymentProvider
from services.recovery.exceptions import CaseNotFoundError
from services.recovery.state_machine import RecoveryStateMachine


def build_read_tools(session: Session, provider: PaymentProvider) -> list[StructuredTool]:
    def get_payment(case_id: str) -> dict:
        """Look up the stored payment/case record for a given case_id."""
        parsed = parse_uuid_or_none(case_id)
        case = session.get(Case, parsed) if parsed else None
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        return {
            "case_id": str(case.id),
            "payment_id": case.payment_id,
            "order_id": case.order_id,
            "amount": str(case.amount),
            "currency": case.currency,
            "payment_method": case.payment_method,
            "failure_code": case.failure_code,
            "failure_reason": case.failure_reason,
            "current_state": case.current_state.value,
        }

    def get_customer_history(customer_id: str) -> dict:
        """Summarize this customer's past cases and their outcomes."""
        cases = session.query(Case).filter(Case.customer_id == customer_id).all()
        outcome_counts: dict[str, int] = {}
        for c in cases:
            outcome_counts[c.current_state.value] = outcome_counts.get(c.current_state.value, 0) + 1
        return {"customer_id": customer_id, "total_cases": len(cases), "outcome_counts": outcome_counts}

    def get_case_history(case_id: str) -> list[dict]:
        """Return this case's full state-transition history in order."""
        parsed = parse_uuid_or_none(case_id)
        if parsed is None:
            return [{"error": f"invalid case_id={case_id}"}]
        sm = RecoveryStateMachine(session)
        try:
            history = sm.history(parsed)
        except CaseNotFoundError:
            return [{"error": f"no case found for case_id={case_id}"}]
        return [
            {
                "from_state": t.from_state.value if t.from_state else None,
                "to_state": t.to_state.value,
                "reason": t.reason,
                "actor": t.actor,
                "created_at": t.created_at.isoformat(),
            }
            for t in history
        ]

    def get_failure_context(case_id: str) -> dict:
        """Return the failure code, reason, payment method, and amount for a case."""
        parsed = parse_uuid_or_none(case_id)
        case = session.get(Case, parsed) if parsed else None
        if case is None:
            return {"error": f"no case found for case_id={case_id}"}
        return {
            "failure_code": case.failure_code,
            "failure_reason": case.failure_reason,
            "payment_method": case.payment_method,
            "amount": str(case.amount),
        }

    def get_historical_recovery_outcomes(
        failure_code: str, payment_method: str, amount: float, action: str,
    ) -> dict:
        """Return empirical success/total counts for this action on similar past cases."""
        from decimal import Decimal

        from models.enums import RecoveryAction

        recovery_action = RecoveryAction(action)
        seg = segment_stats(
            session, failure_code=failure_code, payment_method=payment_method,
            amount=Decimal(str(amount)), action=recovery_action,
        )
        global_stats = global_baseline_stats(session, failure_code=failure_code, action=recovery_action)
        return {
            "dataset": "synthetic evaluation benchmark, not real-world performance",
            "segment": {"successes": seg.successes, "total": seg.total, "rate": seg.empirical_rate},
            "global_for_failure_code": {
                "successes": global_stats.successes, "total": global_stats.total,
                "rate": global_stats.empirical_rate,
            },
        }

    def verify_payment(payment_id: str) -> dict:
        """Check the current payment status with the provider (read-only, non-binding)."""
        try:
            result = provider.verify_payment(payment_id)
        except Exception as exc:
            return {
                "error": str(exc),
                "note": "The provider check itself failed; treat this as unresolved, "
                        "not as a failure or a success.",
            }
        return {
            "mode": result.mode.value,
            "payment_id": result.payment_id,
            "status": result.status,
            "note": "Status check only; does not mark anything as recovered.",
        }

    return [
        tool(get_payment),
        tool(get_customer_history),
        tool(get_case_history),
        tool(get_failure_context),
        tool(get_historical_recovery_outcomes),
        tool(verify_payment),
    ]

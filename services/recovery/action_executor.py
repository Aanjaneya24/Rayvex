
import uuid
from dataclasses import dataclass
from typing import Protocol

from models.enums import RecoveryAction


@dataclass(frozen=True)
class ActionExecutionResult:
    action: RecoveryAction
    simulated: bool
    detail: str


class ActionExecutor(Protocol):
    def execute(self, action: RecoveryAction, *, case_id: uuid.UUID) -> ActionExecutionResult: ...


class SimulatedActionExecutor:
    """The only ActionExecutor implementation that exists. PRD 6.16's
    PaymentProvider is read/verify-only (get_payment, get_order,
    get_payment_status, verify_payment) — there is no "retry this
    payment" or "send this notification" method in the spec, and no real
    channel credentials (SMS/email/WhatsApp gateway) are configured
    anywhere in this environment. Building a real executor against
    nothing behind it would be exactly the kind of fabricated integration
    this project's "never fake a channel" rule forbids.

    What this class buys over inlining the simulated transition directly
    in case_orchestrator.py: a formal swap point. A real executor — once
    a real Action Executor exists to call the Payment Provider or a real
    notification gateway — is a second class satisfying this same
    Protocol; nothing in case_orchestrator.py or its callers changes
    except which one gets constructed.
    """

    def execute(self, action: RecoveryAction, *, case_id: uuid.UUID) -> ActionExecutionResult:
        return ActionExecutionResult(
            action=action, simulated=True,
            detail=f"{action.value} executed (simulated — no Action Executor exists yet)",
        )


def build_default_action_executor() -> ActionExecutor:
    return SimulatedActionExecutor()

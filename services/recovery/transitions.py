
from models.enums import CaseState

TERMINAL_STATES: frozenset[CaseState] = frozenset(
    {CaseState.RECOVERED, CaseState.STOPPED}
)


ALLOWED_TRANSITIONS: dict[CaseState, frozenset[CaseState]] = {
    CaseState.RECEIVED: frozenset({CaseState.SCREENING}),
    CaseState.SCREENING: frozenset(
        {CaseState.DIAGNOSING, CaseState.ESCALATED, CaseState.STOPPED}
    ),
    CaseState.DIAGNOSING: frozenset(
        {CaseState.ELIGIBILITY_CHECK, CaseState.ESCALATED, CaseState.STOPPED}
    ),
    CaseState.ELIGIBILITY_CHECK: frozenset(
        {CaseState.DECISION, CaseState.ESCALATED, CaseState.STOPPED}
    ),
    CaseState.DECISION: frozenset(
        {CaseState.ACTION_PENDING, CaseState.ESCALATED, CaseState.STOPPED}
    ),
    CaseState.ACTION_PENDING: frozenset(
        {CaseState.ACTION_EXECUTED, CaseState.STOPPED}
    ),
    CaseState.ACTION_EXECUTED: frozenset({CaseState.VERIFICATION_PENDING}),
    CaseState.VERIFICATION_PENDING: frozenset(
        {CaseState.RECOVERED, CaseState.FAILED, CaseState.ESCALATED}
    ),
    CaseState.RECOVERED: frozenset(),
    CaseState.FAILED: frozenset(
        {CaseState.VERIFICATION_PENDING, CaseState.DECISION}
    ),
    CaseState.ESCALATED: frozenset(
        {CaseState.ACTION_PENDING, CaseState.STOPPED}
    ),
    CaseState.STOPPED: frozenset(),
}


def is_allowed(from_state: CaseState | None, to_state: CaseState) -> bool:
    if from_state is None:
        return to_state is CaseState.RECEIVED
    return to_state in ALLOWED_TRANSITIONS[from_state]


def is_reconciliation(from_state: CaseState | None, to_state: CaseState) -> bool:
    return from_state is CaseState.FAILED and to_state is CaseState.VERIFICATION_PENDING


def is_retry_reattempt(from_state: CaseState | None, to_state: CaseState) -> bool:
    return from_state is CaseState.FAILED and to_state is CaseState.DECISION


def is_human_review_resume(from_state: CaseState | None, to_state: CaseState) -> bool:
    return from_state is CaseState.ESCALATED and to_state is CaseState.ACTION_PENDING


import inspect

from models.case_state_transition import CaseStateTransition
from models.enums import CaseState
from services.agent.orchestrator import RecoveryAgentOrchestrator
from services.agent.tools.proposal_tools import (
    escalate_case,
    retry_payment,
    send_recovery_link,
    send_recovery_reminder,
    suggest_alternative_payment,
)
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.helpers import (
    drive_case_to_action_pending,
    fake_model_with_responses,
    record_decision_call,
)


def test_action_proposal_tools_have_no_session_or_redis_parameter_at_all():
    for fn in [
        retry_payment, send_recovery_reminder, send_recovery_link,
        suggest_alternative_payment, escalate_case,
    ]:
        params = set(inspect.signature(fn).parameters)
        assert params == {"case_id", "reason"}, (
            f"{fn.__name__} has unexpected parameters {params}; an action "
            f"tool must only ever take the case_id and reason it reports, "
            f"nothing that could reach state."
        )


def test_calling_action_proposal_tools_directly_does_not_touch_the_database():
    result = retry_payment(case_id="anything", reason="testing")
    assert result["status"] == "PROPOSED_NOT_EXECUTED"


def test_agent_proposal_leaves_case_state_completely_unchanged(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    state_before = case.current_state
    transition_count_before = len(sm.history(case.id))
    redis_keys_before = set(redis_client.keys("*"))

    decision_json = (
        '{"action": "RETRY", "reason": "transient timeout, no prior attempts", '
        '"confidence": 0.85, "expected_recovery_value": 90, "risk_level": "LOW"}'
    )
    model = fake_model_with_responses(record_decision_call(decision_json))
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    decision = orchestrator.propose(
        db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id,
    )

    assert decision.action.value == "RETRY"
    assert case.current_state is state_before
    assert case.current_state is CaseState.ACTION_PENDING
    assert len(sm.history(case.id)) == transition_count_before
    assert not any(
        t.actor.startswith("agent") for t in sm.history(case.id)
    )
    redis_keys_after = set(redis_client.keys("*"))
    assert redis_keys_after == redis_keys_before


def test_agent_tools_module_imports_no_state_mutating_functions():
    import services.agent.tools.proposal_tools as proposal_tools
    import services.agent.tools.read_tools as read_tools
    import services.agent.tools.reasoning_tools as reasoning_tools

    forbidden_names = {"record_action_attempt"}
    for module in (proposal_tools, read_tools, reasoning_tools):
        module_globals = set(vars(module))
        assert not (forbidden_names & module_globals), (
            f"{module.__name__} imports a Redis write function directly"
        )

    import inspect as _inspect

    for module in (proposal_tools, read_tools, reasoning_tools):
        source = _inspect.getsource(module)
        assert ".transition(" not in source, (
            f"{module.__name__} calls .transition(...) directly; only "
            f"services/recovery/action_gate.py may do that"
        )

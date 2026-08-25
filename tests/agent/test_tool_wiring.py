
import uuid
from decimal import Decimal

from models.enums import RecoveryAction
from services.agent.tools import build_agent_tools
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.helpers import drive_case_to_action_pending, fake_model_with_responses
from services.agent.orchestrator import RecoveryAgentOrchestrator
from langchain_core.messages import AIMessage

EXPECTED_TOOL_NAMES = {
    "get_payment", "get_customer_history", "get_case_history", "get_failure_context",
    "get_historical_recovery_outcomes", "verify_payment", "predict_recovery_probability",
    "calculate_expected_value", "check_risk", "check_policy", "choose_recovery_action",
    "retry_payment", "send_recovery_reminder", "send_recovery_link",
    "suggest_alternative_payment", "escalate_case", "record_decision",
}


def test_full_prd_67_tool_set_is_present(db_session, redis_client):
    tools = build_agent_tools(
        db_session, redis_client, case_id=uuid.uuid4(), correlation_id=uuid.uuid4(),
        model_backend="test", model_name="test-model", prompt_version="v1",
        schema_version="v1", tool_trace=[],
    )
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES


def test_predict_recovery_probability_tool_uses_real_estimator(db_session, redis_client):
    from services.recovery.recovery_config_repository import (
        DEFAULT_RECOVERY_CONFIG,
        activate_new_recovery_config_version,
    )

    activate_new_recovery_config_version(
        db_session, merchant_id=None, created_by="test",
        **{**DEFAULT_RECOVERY_CONFIG, "min_sample_size": 5},
    )
    from services.evaluation.dataset import GeneratedOutcome, persist_synthetic_outcomes

    persist_synthetic_outcomes(db_session, [
        GeneratedOutcome(
            seed=1, merchant_id="merchant_1", customer_id="cust_1", payment_method="card",
            failure_category="transient", failure_code="bank_timeout", amount=Decimal("1000.00"),
            retry_count_at_action_time=0, risk_score=0.1, action_taken=RecoveryAction.RETRY,
            recovered=(i < 4),
        )
        for i in range(6)
    ])

    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=Decimal("1000.00"))

    tools = build_agent_tools(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        model_backend="test", model_name="test-model", prompt_version="v1",
        schema_version="v1", tool_trace=[],
    )
    predict = next(t for t in tools if t.name == "predict_recovery_probability")
    result = predict.invoke({"case_id": str(case.id), "action": "RETRY"})

    assert result["source_tier"] == "merchant_specific"
    assert result["sample_size"] == 6
    assert abs(result["probability"] - (4 + 1) / (6 + 1 + 1)) < 1e-9


def test_multi_step_tool_calling_loop_threads_results_correctly(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=Decimal("500.00"))

    turn_1 = AIMessage(
        content="", tool_calls=[{"name": "get_payment", "args": {"case_id": str(case.id)}, "id": "1"}]
    )
    turn_2 = AIMessage(
        content="", tool_calls=[{
            "name": "record_decision",
            "args": {"decision_json": (
                '{"action": "RETRY", "reason": "confirmed via get_payment", '
                '"confidence": 0.8, "expected_recovery_value": 400, "risk_level": "LOW"}'
            )},
            "id": "2",
        }],
    )
    model = fake_model_with_responses(turn_1, turn_2)
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    decision = orchestrator.propose(
        db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id,
    )

    assert decision.action.value == "RETRY"
    assert decision.reason == "confirmed via get_payment"


from models.agent_decision import AgentDecision
from services.agent.orchestrator import RecoveryAgentOrchestrator
from services.agent.prompts.system_prompt import PROMPT_VERSION
from services.agent.schema import SCHEMA_VERSION
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.fakes import FakeToolCallingChatModel
from tests.agent.helpers import drive_case_to_action_pending, record_decision_call


def test_agent_decision_row_carries_real_model_and_version_fields(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    decision_json = (
        '{"action": "RETRY", "reason": "transient timeout", "confidence": 0.8, '
        '"expected_recovery_value": 80, "risk_level": "LOW"}'
    )
    model = FakeToolCallingChatModel(responses=[record_decision_call(decision_json)])
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    orchestrator.propose(db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id)

    row = db_session.query(AgentDecision).filter_by(case_id=case.id).one()
    assert row.model_backend == "FakeToolCallingChatModel"
    assert row.model_name == "FakeToolCallingChatModel"
    assert row.prompt_version == PROMPT_VERSION == "v1"
    assert row.schema_version == SCHEMA_VERSION == "v1"


def test_a_real_backend_records_its_actual_model_identifier_not_just_the_class(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    from services.agent.orchestrator import build_llm

    llm = build_llm()
    model_name = getattr(llm, "model_name", None) or type(llm).__name__
    assert model_name == "llama-3.3-70b-versatile"
    assert model_name != type(llm).__name__

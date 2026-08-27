import uuid

from models.enums import RecoveryAction
from services.recovery.action_executor import SimulatedActionExecutor, build_default_action_executor


def test_simulated_executor_marks_the_result_as_simulated():
    result = SimulatedActionExecutor().execute(RecoveryAction.RETRY, case_id=uuid.uuid4())
    assert result.simulated is True
    assert result.action is RecoveryAction.RETRY
    assert "simulated" in result.detail.lower()


def test_default_executor_is_the_simulated_one():
    assert isinstance(build_default_action_executor(), SimulatedActionExecutor)

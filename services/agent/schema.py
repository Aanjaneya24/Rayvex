
from pydantic import BaseModel, ConfigDict, Field

from models.enums import RecoveryAction, RiskLevel

SCHEMA_VERSION = "v1"


class AgentDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: RecoveryAction
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    expected_recovery_value: float
    risk_level: RiskLevel

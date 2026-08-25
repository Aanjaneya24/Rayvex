import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import RecoveryAction, RiskLevel

if TYPE_CHECKING:
    from models.case import Case


class AgentDecision(Base):

    __tablename__ = "agent_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    proposed_action: Mapped[RecoveryAction] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=False
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    expected_recovery_value: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="risk_level", native_enum=True), nullable=False
    )

    model_backend: Mapped[str] = mapped_column(String, nullable=False)

    model_name: Mapped[str] = mapped_column(String, nullable=False)

    prompt_version: Mapped[str] = mapped_column(String, nullable=False)

    schema_version: Mapped[str] = mapped_column(String, nullable=False)

    tool_trace: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    case: Mapped["Case"] = relationship()

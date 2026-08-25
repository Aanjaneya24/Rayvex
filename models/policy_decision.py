import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import PolicyVerdictType, RecoveryAction

if TYPE_CHECKING:
    from models.case import Case
    from models.policy_config import PolicyConfig


class PolicyDecision(Base):

    __tablename__ = "policy_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    policy_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_configs.id"), nullable=False
    )
    policy_config_version: Mapped[int] = mapped_column(Integer, nullable=False)

    proposed_action: Mapped[RecoveryAction] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=False
    )
    verdict_type: Mapped[PolicyVerdictType] = mapped_column(
        Enum(PolicyVerdictType, name="policy_verdict_type", native_enum=True),
        nullable=False,
    )
    resulting_action: Mapped[RecoveryAction | None] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=True
    )

    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    requires_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    case: Mapped["Case"] = relationship()
    policy_config: Mapped["PolicyConfig"] = relationship()

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import HumanReviewDecision, RecoveryAction

if TYPE_CHECKING:
    from models.case_state_transition import CaseStateTransition


class HumanReviewAction(Base):

    __tablename__ = "human_review_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    reviewer: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[HumanReviewDecision] = mapped_column(
        Enum(HumanReviewDecision, name="human_review_decision", native_enum=True), nullable=False
    )
    original_proposed_action: Mapped[RecoveryAction | None] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=True
    )
    final_action: Mapped[RecoveryAction | None] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=True
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)

    resulting_transition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_state_transitions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    resulting_transition: Mapped["CaseStateTransition | None"] = relationship()

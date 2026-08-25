import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import CaseState

if TYPE_CHECKING:
    from models.case import Case
    from models.payment_event import PaymentEvent
    from models.policy_decision import PolicyDecision


class CaseStateTransition(Base):

    __tablename__ = "case_state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )

    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    from_state: Mapped[CaseState | None] = mapped_column(
        Enum(CaseState, name="case_state", native_enum=True), nullable=True
    )
    to_state: Mapped[CaseState] = mapped_column(
        Enum(CaseState, name="case_state", native_enum=True), nullable=False
    )

    reason: Mapped[str] = mapped_column(String, nullable=False)

    actor: Mapped[str] = mapped_column(String, nullable=False)

    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    triggering_payment_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_events.id"), nullable=True
    )

    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_decisions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    case: Mapped["Case"] = relationship(back_populates="transitions")
    triggering_payment_event: Mapped["PaymentEvent | None"] = relationship()
    policy_decision: Mapped["PolicyDecision | None"] = relationship()

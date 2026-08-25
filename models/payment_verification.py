import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import ProviderMode, VerificationOutcome

if TYPE_CHECKING:
    from models.case import Case
    from models.case_state_transition import CaseStateTransition


class PaymentVerification(Base):

    __tablename__ = "payment_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    payment_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    mode: Mapped[ProviderMode] = mapped_column(
        Enum(ProviderMode, name="provider_mode", native_enum=True), nullable=False
    )
    provider_status: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[VerificationOutcome] = mapped_column(
        Enum(VerificationOutcome, name="verification_outcome", native_enum=True), nullable=False
    )

    raw_response: Mapped[dict] = mapped_column(JSONB, nullable=False)

    resulting_transition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_state_transitions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    case: Mapped["Case"] = relationship()
    resulting_transition: Mapped["CaseStateTransition | None"] = relationship()

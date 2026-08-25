import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base
from models.enums import CaseState, CaseType

if TYPE_CHECKING:
    from models.case_state_transition import CaseStateTransition
    from models.payment_event import PaymentEvent


class Case(Base):

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    correlation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    case_type: Mapped[CaseType] = mapped_column(
        Enum(CaseType, name="case_type", native_enum=True), nullable=False
    )

    merchant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    payment_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    amount: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    payment_method: Mapped[str | None] = mapped_column(String, nullable=True)

    failure_code: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    current_state: Mapped[CaseState] = mapped_column(
        Enum(CaseState, name="case_state", native_enum=True),
        nullable=False,
        default=CaseState.RECEIVED,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    payment_events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="case", order_by="PaymentEvent.timestamp"
    )
    transitions: Mapped[list["CaseStateTransition"]] = relationship(
        back_populates="case", order_by="CaseStateTransition.created_at"
    )

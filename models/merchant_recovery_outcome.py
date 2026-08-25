import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import RecoveryAction


class MerchantRecoveryOutcome(Base):

    __tablename__ = "merchant_recovery_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True
    )
    merchant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    failure_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String, nullable=False, index=True)
    amount: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    action_taken: Mapped[RecoveryAction] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=False
    )
    recovered: Mapped[bool] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

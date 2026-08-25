import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import RecoveryAction


class SyntheticRecoveryOutcome(Base):

    __tablename__ = "synthetic_recovery_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    seed: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    merchant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    payment_method: Mapped[str] = mapped_column(String, nullable=False, index=True)
    failure_category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    failure_code: Mapped[str] = mapped_column(String, nullable=False, index=True)

    amount: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    retry_count_at_action_time: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)

    action_taken: Mapped[RecoveryAction] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=False
    )
    recovered: Mapped[bool] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.enums import RecoveryAction


class ABExperimentRun(Base):

    __tablename__ = "ab_experiment_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    failure_code: Mapped[str] = mapped_column(String, nullable=False)
    payment_method: Mapped[str] = mapped_column(String, nullable=False)
    action_a: Mapped[RecoveryAction] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=False
    )
    action_b: Mapped[RecoveryAction] = mapped_column(
        Enum(RecoveryAction, name="recovery_action", native_enum=True), nullable=False
    )

    sample_size_a: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_size_b: Mapped[int] = mapped_column(Integer, nullable=False)
    successes_a: Mapped[int] = mapped_column(Integer, nullable=False)
    successes_b: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_rate_a: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_rate_b: Mapped[float] = mapped_column(Float, nullable=False)
    revenue_a: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    revenue_b: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cost_per_recovered_rupee_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_per_recovered_rupee_b: Mapped[float | None] = mapped_column(Float, nullable=True)

    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    significance_level: Mapped[float] = mapped_column(Float, nullable=False)
    result: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

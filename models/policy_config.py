import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PolicyConfig(Base):

    __tablename__ = "policy_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    merchant_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


    max_retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_automated_recovery_amount: Mapped[Numeric] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    max_daily_attempts_per_customer: Mapped[int] = mapped_column(Integer, nullable=False)

    prohibited_retry_failure_codes: Mapped[list] = mapped_column(JSONB, nullable=False)

    suspicious_velocity_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    suspicious_velocity_window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    high_value_threshold: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)

    allowed_actions_by_failure_code: Mapped[dict] = mapped_column(JSONB, nullable=False)

    allowed_communication_hours_start: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_communication_hours_end: Mapped[int] = mapped_column(Integer, nullable=False)

    max_interventions_per_case: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score_threshold: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index(
            "uq_policy_configs_active_per_merchant",
            "merchant_id",
            unique=True,
            postgresql_where=text("is_active"),
            postgresql_nulls_not_distinct=True,
        ),
    )

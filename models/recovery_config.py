import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RecoveryConfig(Base):

    __tablename__ = "recovery_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    merchant_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    default_probability_by_action: Mapped[dict] = mapped_column(JSONB, nullable=False)

    action_cost_by_action: Mapped[dict] = mapped_column(JSONB, nullable=False)

    risk_cost_multiplier: Mapped[float] = mapped_column(Float, nullable=False)

    min_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)

    smoothing_alpha: Mapped[float] = mapped_column(Float, nullable=False)
    smoothing_beta: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index(
            "uq_recovery_configs_active_per_merchant",
            "merchant_id",
            unique=True,
            postgresql_where=text("is_active"),
            postgresql_nulls_not_distinct=True,
        ),
    )

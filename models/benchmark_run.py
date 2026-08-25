import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class BenchmarkRun(Base):

    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)

    naive_retry_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    intelligent_recovery_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    unnecessary_actions_avoided: Mapped[int] = mapped_column(Integer, nullable=False)
    incremental_verified_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class MLModelRun(Base):

    __tablename__ = "ml_model_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    train_size: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_size: Mapped[int] = mapped_column(Integer, nullable=False)
    test_size: Mapped[int] = mapped_column(Integer, nullable=False)

    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    feature_importance: Mapped[dict] = mapped_column(JSONB, nullable=False)

    categories: Mapped[dict] = mapped_column(JSONB, nullable=False)

    model_path: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

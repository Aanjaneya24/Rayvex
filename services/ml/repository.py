
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.ml_model_run import MLModelRun


def get_active_model_run(session: Session) -> MLModelRun | None:
    stmt = select(MLModelRun).where(MLModelRun.is_active.is_(True)).order_by(MLModelRun.created_at.desc())
    return session.execute(stmt).scalars().first()


def deactivate_all_model_runs(session: Session) -> None:
    session.execute(update(MLModelRun).where(MLModelRun.is_active.is_(True)).values(is_active=False))
    session.flush()

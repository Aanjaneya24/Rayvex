
from collections.abc import Generator

import redis

from models.session import SessionLocal
from services.policy.redis_client import make_redis_client

_redis_client: redis.Redis | None = None


def get_db() -> Generator:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = make_redis_client()
    return _redis_client

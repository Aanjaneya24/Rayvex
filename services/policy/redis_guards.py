
import time
import uuid
from datetime import datetime, timezone

import redis

_COOLDOWN_KEY = "cooldown:case:{case_id}"
_VELOCITY_KEY = "velocity:customer:{customer_id}"
_DAILY_ATTEMPTS_KEY = "daily_attempts:customer:{customer_id}:{date}"

_DAILY_ATTEMPTS_TTL_SECONDS = 2 * 24 * 60 * 60


def record_action_attempt(
    client: redis.Redis,
    *,
    case_id: uuid.UUID,
    customer_id: str,
    cooldown_seconds: int,
    velocity_window_seconds: int,
) -> None:
    now = time.time()

    client.set(_COOLDOWN_KEY.format(case_id=case_id), now, ex=cooldown_seconds)

    velocity_key = _VELOCITY_KEY.format(customer_id=customer_id)
    client.zadd(velocity_key, {str(uuid.uuid4()): now})
    client.expire(velocity_key, velocity_window_seconds)

    daily_key = _DAILY_ATTEMPTS_KEY.format(
        customer_id=customer_id, date=datetime.now(timezone.utc).date().isoformat()
    )
    client.incr(daily_key)
    client.expire(daily_key, _DAILY_ATTEMPTS_TTL_SECONDS)


def is_cooldown_satisfied(client: redis.Redis, case_id: uuid.UUID) -> bool:
    return client.get(_COOLDOWN_KEY.format(case_id=case_id)) is None


def compute_suspicious_velocity(
    client: redis.Redis, *, customer_id: str, window_seconds: int, threshold: int
) -> bool:
    velocity_key = _VELOCITY_KEY.format(customer_id=customer_id)
    now = time.time()
    client.zremrangebyscore(velocity_key, 0, now - window_seconds)
    count = client.zcard(velocity_key)
    return count >= threshold


def get_daily_attempts_count(client: redis.Redis, customer_id: str) -> int:
    daily_key = _DAILY_ATTEMPTS_KEY.format(
        customer_id=customer_id, date=datetime.now(timezone.utc).date().isoformat()
    )
    value = client.get(daily_key)
    return int(value) if value is not None else 0

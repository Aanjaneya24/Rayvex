
import time

import redis
from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 120
_KEY_TEMPLATE = "rate_limit:webhook:{ip}:{window}"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    redis_client: redis.Redis, request: Request, *,
    window_seconds: int | None = None, max_requests: int | None = None,
) -> None:
    window_seconds = window_seconds if window_seconds is not None else _WINDOW_SECONDS
    max_requests = max_requests if max_requests is not None else _MAX_REQUESTS_PER_WINDOW
    ip = _client_ip(request)
    window = int(time.time()) // window_seconds
    key = _KEY_TEMPLATE.format(ip=ip, window=window)

    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window_seconds)

    if count > max_requests:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: more than {max_requests} requests in {window_seconds}s from this source.",
        )

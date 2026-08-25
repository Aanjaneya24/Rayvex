
import os

import redis
from dotenv import load_dotenv

load_dotenv()


def get_redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL is not set. Copy .env.example to .env and fill it in.")
    return url


def make_redis_client(url: str | None = None) -> redis.Redis:
    return redis.Redis.from_url(url or get_redis_url(), decode_responses=True)

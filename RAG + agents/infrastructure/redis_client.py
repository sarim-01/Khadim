"""
Build a synchronous Redis client in one place.

Railway Redis plugin exposes REDIS_URL; older code paths only read REDIS_HOST / REDIS_PORT.
This helper prefers REDIS_URL when set, so all modules behave the same as main.py's client.
"""

import os

import redis


def get_sync_redis(
    *,
    decode_responses: bool = True,
    socket_connect_timeout: float | int = 5,
    socket_timeout: float | int = 5,
    retry_on_timeout: bool = True,
) -> redis.StrictRedis:
    """Return StrictRedis connected to Railway (REDIS_URL) or host/port."""

    url = (os.getenv("REDIS_URL") or "").strip()
    if url:
        return redis.StrictRedis.from_url(
            url,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            retry_on_timeout=retry_on_timeout,
        )

    host = (os.getenv("REDIS_HOST") or "127.0.0.1").strip()
    raw_port = os.getenv("REDIS_PORT") or os.getenv("REDISPORT") or "6379"
    port = int(str(raw_port).strip() or "6379")

    return redis.StrictRedis(
        host=host,
        port=port,
        db=0,
        decode_responses=decode_responses,
        socket_connect_timeout=socket_connect_timeout,
        socket_timeout=socket_timeout,
        retry_on_timeout=retry_on_timeout,
    )

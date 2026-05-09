"""Redis connection utilities."""

from infrastructure.redis_client import get_sync_redis


class RedisConnection:
    """Singleton Redis connection class."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls._create_instance()
        return cls._instance

    @staticmethod
    def _create_instance():
        r = get_sync_redis()
        # Fail fast if Redis isn't reachable (same expectation as before)
        r.ping()
        return r
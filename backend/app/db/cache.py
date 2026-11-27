from redis.asyncio import Redis

from app.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis(
        host=settings.app_redis_host,
        port=settings.app_redis_port,
        db=settings.app_redis_db,
        username=settings.app_redis_username,
        password=settings.redis_password.get_secret_value() if settings.redis_password else None,
        socket_connect_timeout=settings.app_probe_timeout,
        socket_timeout=settings.app_probe_timeout,
        decode_responses=True,
    )

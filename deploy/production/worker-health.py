"""Check the dependencies of the running task container."""
import asyncio

from app.core.config import Settings
from app.db.cache import create_redis_client
from app.db.postgres import create_database_engine
from app.repositories.health import HealthRepository
from app.services.health import HealthService


async def main() -> int:
    settings = Settings()
    engine = create_database_engine(settings)
    redis = create_redis_client(settings)
    try:
        result = await HealthService(HealthRepository(engine, redis), 3).readiness()
        return 0 if result.status == "ready" else 1
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

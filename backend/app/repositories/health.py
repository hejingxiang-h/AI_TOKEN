from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class HealthRepository:
    def __init__(self, database: AsyncEngine, cache: Redis) -> None:
        self.database = database
        self.cache = cache

    async def ping_database(self) -> None:
        async with self.database.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def ping_cache(self) -> None:
        if not await self.cache.ping():
            raise RuntimeError("Redis did not acknowledge PING")

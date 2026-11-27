import json
import logging
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.gateway import finalize

logger = logging.getLogger(__name__)
JOURNAL = "gateway:settlement-journal"


async def journal(cache: Redis, request_id: UUID, payload: dict[str, Any]) -> None:
    try:
        await cache.hset(JOURNAL, request_id.hex, json.dumps(payload))
    except RedisError:
        logger.warning("settlement journal unavailable", extra={"request_id": request_id.hex})


async def forget(cache: Redis, request_id: UUID) -> None:
    try:
        await cache.hdel(JOURNAL, request_id.hex)
    except RedisError:
        logger.warning("settlement journal cleanup pending", extra={"request_id": request_id.hex})


async def recover_journal(factory: async_sessionmaker, cache: Redis, cursor: int = 0) -> int:
    cursor, entries = await cache.hscan(JOURNAL, cursor=cursor, count=50)
    for key, value in entries.items():
        try:
            request_id = UUID(key)
            await finalize(factory, request_id, **json.loads(value))
        except Exception:
            logger.warning("settlement recovery pending", extra={"request_id": key})
        else:
            await forget(cache, request_id)
    return cursor

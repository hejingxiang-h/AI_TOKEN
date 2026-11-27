from uuid import UUID

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

# All keys share a hash slot for Redis Cluster; admission checks and updates are atomic.
ACQUIRE = """
local now = tonumber(redis.call('TIME')[1])
local minute = math.floor(now / 60)
local tokens = tonumber(ARGV[1])
local lease = tonumber(ARGV[2])
local member = ARGV[3]
for i = 1, #KEYS, 2 do
  local counter = KEYS[i]
  local rpm = tonumber(ARGV[4 + (i-1)/2])
  local stored_minute = tonumber(redis.call('HGET', counter, 'minute') or '-1')
  if stored_minute ~= minute then
    redis.call('DEL', counter)
  end
  redis.call('ZREMRANGEBYSCORE', KEYS[i+1], '-inf', now)
  if tonumber(redis.call('HGET', counter, 'rpm') or '0') >= rpm
     or tonumber(redis.call('HGET', counter, 'tpm') or '0') + tokens > tonumber(ARGV[4 + #KEYS/2])
     or redis.call('ZCARD', KEYS[i+1]) >= tonumber(ARGV[5 + #KEYS/2]) then
    return 0
  end
end
for i = 1, #KEYS, 2 do
  local counter = KEYS[i]
  redis.call('HSET', counter, 'minute', minute)
  redis.call('HINCRBY', counter, 'rpm', 1)
  redis.call('HINCRBY', counter, 'tpm', tokens)
  redis.call('EXPIRE', counter, 125)
  redis.call('ZADD', KEYS[i+1], now + lease, member)
  redis.call('EXPIRE', KEYS[i+1], lease + 5)
end
return 1
"""


def rate_keys(scopes: list[str]) -> list[str]:
    return [
        f"gateway:{{inference}}:{scope}:{kind}" for scope in scopes for kind in ("rate", "lease")
    ]


async def acquire(
    cache: Redis,
    request_id: UUID,
    scopes: dict[str, int],
    tokens: int,
    lease: int,
    tpm: int,
    parallel: int,
) -> None:
    keys = rate_keys(list(scopes))
    try:
        result = await cache.eval(
            ACQUIRE,
            len(keys),
            *keys,
            tokens,
            lease,
            str(request_id),
            *scopes.values(),
            tpm,
            parallel,
        )
    except RedisError as exc:
        raise HTTPException(503, "Request admission unavailable") from exc
    if result != 1:
        raise HTTPException(
            429, "Request rate or concurrency exceeded", headers={"Retry-After": "60"}
        )


async def release(cache: Redis, request_id: UUID, scopes: dict[str, int]) -> None:
    try:
        async with cache.pipeline(transaction=False) as pipe:
            for key in rate_keys(list(scopes))[1::2]:
                pipe.zrem(key, str(request_id))
            await pipe.execute()
    except RedisError:
        # The absolute request deadline precedes lease expiration.
        return

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from app.repositories.health import HealthRepository
from app.schemas.health import DependencyCheck, HealthChecks, Readiness

logger = logging.getLogger(__name__)


class HealthService:
    def __init__(self, repository: HealthRepository, timeout: float) -> None:
        self.repository = repository
        self.timeout = timeout

    async def readiness(self) -> Readiness:
        database, cache = await asyncio.gather(
            self._probe("postgresql", self.repository.ping_database),
            self._probe("redis", self.repository.ping_cache),
        )
        return Readiness(
            status="ready" if database.status == cache.status == "up" else "not_ready",
            checks=HealthChecks(postgresql=database, redis=cache),
        )

    async def _probe(
        self, dependency: str, probe: Callable[[], Awaitable[None]]
    ) -> DependencyCheck:
        started = perf_counter()
        try:
            async with asyncio.timeout(self.timeout):
                await probe()
        except Exception as exc:
            logger.warning(
                "dependency_unavailable",
                extra={"dependency": dependency, "error_type": type(exc).__name__},
            )
            return DependencyCheck(status="down", latency_ms=self._elapsed(started))
        return DependencyCheck(status="up", latency_ms=self._elapsed(started))

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((perf_counter() - started) * 1000, 2)

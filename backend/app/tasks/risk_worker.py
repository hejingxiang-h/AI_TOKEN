import argparse
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.config import Settings
from app.db.cache import create_redis_client
from app.db.postgres import create_database_engine, create_session_factory
from app.services.gateway import reconcile_stale
from app.services.gateway_recovery import recover_journal
from app.services.risk import reconcile_risk

logger = logging.getLogger(__name__)
LOCK_ID = 63410029


async def run(once: bool) -> None:
    settings = Settings()
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    cache = create_redis_client(settings)
    cursor = 0
    try:
        while True:
            try:
                # Dedicated connection holds the lock across the independent settlement sessions.
                async with engine.connect() as owner:
                    acquired = await owner.scalar(text(f"SELECT pg_try_advisory_lock({LOCK_ID})"))
                    if acquired:
                        try:
                            try:
                                cursor = await recover_journal(factory, cache, cursor)
                            except Exception:
                                logger.warning("settlement journal unavailable")
                            await reconcile_stale(factory, settings.app_gateway_deadline)
                            async with factory.begin() as db:
                                await reconcile_risk(
                                    db,
                                    datetime.now(UTC),
                                    settings.app_risk_frequency,
                                    settings.app_risk_high_cost_usd,
                                    settings.app_risk_provider_errors,
                                    settings.app_risk_invalid_keys,
                                )
                        finally:
                            await owner.execute(text(f"SELECT pg_advisory_unlock({LOCK_ID})"))
            except Exception:
                logger.exception("risk worker iteration failed")
                if once:
                    raise
            if once:
                return
            await asyncio.sleep(2 if cursor else settings.app_risk_interval)
    finally:
        await cache.aclose()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(parser.parse_args().once))


if __name__ == "__main__":
    main()

import ipaddress
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.permissions import Principal
from app.models.organization import Role
from app.models.risk import RiskAlert, RiskSignal

logger = logging.getLogger(__name__)


def source_ip(host: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def client_type(agent: str) -> str:
    agent = agent[:512].lower()
    for label, markers in (
        ("codex", ("codex",)),
        ("claude_code", ("claude-code",)),
        ("openai_sdk", ("openai-python", "openai-node")),
        ("anthropic_sdk", ("anthropic-python", "anthropic-node")),
        ("curl", ("curl/",)),
        ("browser", ("mozilla/",)),
    ):
        if any(item in agent for item in markers):
            return label
    return "unknown"


async def signal(factory: async_sessionmaker, kind: str, source: str) -> None:
    minute = datetime.now(UTC).replace(second=0, microsecond=0)
    try:
        async with factory.begin() as db:
            statement = insert(RiskSignal).values(kind=kind, source=source, minute=minute, count=1)
            await db.execute(
                statement.on_conflict_do_update(
                    index_elements=[RiskSignal.kind, RiskSignal.source, RiskSignal.minute],
                    set_={"count": RiskSignal.count + 1},
                )
            )
    except Exception:
        logger.warning("risk signal persistence unavailable", extra={"signal_kind": kind})


class RiskRepository:
    def __init__(self, db: AsyncSession, actor: Principal) -> None:
        self.db = db
        self.actor = actor

    def alerts(self):
        query = select(RiskAlert)
        if self.actor.role == Role.SUPER_ADMIN:
            return query
        return query.where(self.actor.within(RiskAlert.user_id, RiskAlert.department_id))

    async def get(self, target: UUID, *, lock: bool = False) -> RiskAlert | None:
        query = self.alerts().where(RiskAlert.id == target)
        return await self.db.scalar(query.with_for_update() if lock else query)


async def emit(
    db: AsyncSession,
    fingerprint: str,
    kind: str,
    severity: str,
    target_type: str,
    now: datetime,
    evidence: dict,
    target_id: UUID | None = None,
    *,
    user_id: UUID | None = None,
    department_id: UUID | None = None,
) -> None:
    statement = insert(RiskAlert).values(
        fingerprint=fingerprint,
        kind=kind,
        severity=severity,
        target_type=target_type,
        target_id=target_id,
        user_id=user_id,
        department_id=department_id,
        evidence=evidence,
        detected_at=now,
        last_seen_at=now,
        status="pending",
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[RiskAlert.fingerprint],
            set_={
                "last_seen_at": statement.excluded.last_seen_at,
                "evidence": statement.excluded.evidence,
            },
        )
    )

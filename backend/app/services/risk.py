from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access import QuotaRule
from app.models.gateway import GatewayEvent
from app.models.gateway import GatewayRequest as Call
from app.models.risk import RiskAlert, RiskSignal
from app.repositories.risk import emit

SCOPE_COLUMNS = {
    "department": Call.department_id,
    "project": Call.project_id,
    "user": Call.user_id,
    "key": Call.key_id,
}
PROXY_ERRORS = ("upstream_timeout", "upstream_error", "upstream_rejected")


async def quota_alerts(db: AsyncSession, now: datetime) -> None:
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    amount = case(
        (Call.settlement == "settled", Call.platform_cost),
        (Call.settlement.in_(["reserved", "review"]), Call.reserved_cost),
        else_=0,
    )
    for rule in await db.scalars(select(QuotaRule)):
        target = getattr(rule, rule.scope + "_id", None)
        query = select(
            func.coalesce(func.sum(amount).filter(Call.started_at >= day), 0),
            func.coalesce(func.sum(amount), 0),
        ).where(
            Call.started_at >= month,
            Call.started_at <= now,
            Call.currency == "USD",
        )
        if rule.scope in SCOPE_COLUMNS:
            query = query.where(SCOPE_COLUMNS[rule.scope] == target)
        daily, monthly = (await db.execute(query)).one()
        for period, start, exposure, limit in (
            ("daily", day, daily, rule.daily_amount),
            ("monthly", month, monthly, rule.monthly_amount),
        ):
            for threshold in (80, 90, 100):
                if exposure * 100 >= limit * threshold:
                    await emit(
                        db,
                        f"quota:{rule.id}:{period}:{start.date()}:{threshold}",
                        "quota_threshold",
                        "high" if threshold == 100 else "warning",
                        rule.scope,
                        now,
                        {
                            "period": period,
                            "start": str(start.date()),
                            "threshold": threshold,
                            "exposure": str(exposure),
                            "limit": str(limit),
                            "currency": "USD",
                        },
                        target,
                        user_id=rule.user_id,
                        department_id=rule.department_id,
                    )


async def call_alerts(
    db: AsyncSession, now: datetime, frequency: int, high_cost: Decimal, failures: int
) -> None:
    lower = now - timedelta(minutes=5)
    bucket = int(now.timestamp()) // 300
    recent = Call.started_at >= lower
    grouped = await db.execute(
        select(Call.key_id, Call.user_id, Call.department_id, func.count())
        .where(recent)
        .group_by(Call.key_id, Call.user_id, Call.department_id)
        .having(func.count() >= frequency)
    )
    for key, user, department, count in grouped:
        await emit(
            db,
            f"frequency:{key}:{bucket}",
            "high_frequency",
            "warning",
            "key",
            now,
            {"count": count, "window_minutes": 5},
            key,
            user_id=user,
            department_id=department,
        )
        await db.execute(
            update(Call).where(recent, Call.key_id == key).values(risk_state="flagged")
        )
    grouped = await db.execute(
        select(Call.provider_id, func.count())
        .where(recent, Call.status.in_(PROXY_ERRORS))
        .group_by(Call.provider_id)
        .having(func.count() >= failures)
    )
    for provider, count in grouped:
        await emit(
            db,
            f"provider:{provider}:{bucket}",
            "provider_errors",
            "high",
            "provider",
            now,
            {"count": count, "window_minutes": 5},
            provider,
        )
        await db.execute(
            update(Call)
            .where(recent, Call.provider_id == provider, Call.status.in_(PROXY_ERRORS))
            .values(risk_state="flagged")
        )
    groups = await db.execute(
        select(Call.user_id, Call.department_id, func.sum(Call.platform_cost))
        .where(recent, Call.settlement == "settled", Call.currency == "USD")
        .group_by(Call.user_id, Call.department_id)
        .having(func.sum(Call.platform_cost) >= high_cost)
    )
    for user, department, cost in groups:
        await emit(
            db,
            f"spend:{user}:{department}:{bucket}",
            "high_spend",
            "warning",
            "user",
            now,
            {"cost": str(cost), "currency": "USD", "window_minutes": 5},
            user,
            user_id=user,
            department_id=department,
        )
        await db.execute(
            update(Call)
            .where(recent, Call.user_id == user, Call.department_id == department)
            .values(risk_state="flagged")
        )
    review = await db.execute(
        select(GatewayEvent.kind, Call.id, Call.user_id, Call.department_id)
        .join(Call, Call.id == GatewayEvent.request_id)
        .where(
            GatewayEvent.created_at >= lower,
            GatewayEvent.kind.in_(("needs_review", "reservation_exceeded")),
        )
    )
    for kind, request_id, user, department in review:
        await emit(
            db,
            f"settlement:{kind}:{request_id}",
            "settlement_failure",
            "high",
            "request",
            now,
            {"reason": kind},
            request_id,
            user_id=user,
            department_id=department,
        )
        await db.execute(update(Call).where(Call.id == request_id).values(risk_state="flagged"))


async def signal_alerts(db: AsyncSession, now: datetime, invalid_limit: int) -> None:
    lower = now - timedelta(minutes=5)
    bucket = int(now.timestamp()) // 300
    groups = await db.execute(
        select(RiskSignal.kind, RiskSignal.source, func.sum(RiskSignal.count))
        .where(RiskSignal.minute >= lower.replace(second=0, microsecond=0))
        .group_by(RiskSignal.kind, RiskSignal.source)
    )
    for kind, source, count in groups:
        if kind == "invalid_key" and count < invalid_limit:
            continue
        await emit(
            db,
            f"signal:{kind}:{source}:{bucket}",
            kind,
            "high",
            "gateway",
            now,
            {
                "count": count,
                "window_minutes": 5,
                **({"source_ip": source} if kind == "invalid_key" else {}),
            },
        )
    await db.execute(delete(RiskSignal).where(RiskSignal.minute < now - timedelta(days=7)))


async def reconcile_invoices(db: AsyncSession, now: datetime) -> None:
    rows = await db.execute(
        select(
            Call.id,
            Call.user_id,
            Call.department_id,
            Call.currency,
            Call.platform_cost,
            Call.supplier_cost,
        )
        .where(
            Call.settlement == "settled",
            Call.supplier_cost.is_not(None),
            Call.platform_cost.is_not(None),
            Call.platform_cost != Call.supplier_cost,
            ~select(RiskAlert.id)
            .where(RiskAlert.fingerprint == func.concat("invoice:", Call.id))
            .exists(),
        )
        .limit(500)
    )
    for request_id, user, department, currency, platform, supplier in rows:
        await emit(
            db,
            f"invoice:{request_id}",
            "invoice_mismatch",
            "warning",
            "request",
            now,
            {"currency": currency, "platform_cost": str(platform), "supplier_cost": str(supplier)},
            request_id,
            user_id=user,
            department_id=department,
        )


async def reconcile_risk(
    db: AsyncSession,
    now: datetime,
    frequency: int,
    high_cost: Decimal,
    failures: int,
    invalid_limit: int,
) -> None:
    await quota_alerts(db, now)
    await call_alerts(db, now, frequency, high_cost, failures)
    await signal_alerts(db, now, invalid_limit)
    await reconcile_invoices(db, now)

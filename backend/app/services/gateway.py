import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.integrations.gateway_limits import acquire, release
from app.models.access import ApiKey
from app.models.gateway import GatewayEvent, GatewayRequest
from app.models.model_catalog import PriceVersion
from app.repositories.gateway import GatewayRepository
from app.schemas.gateway import Protocol, UsageEvent
from app.services.gateway_usage import clean_usage, cost, normalize, upper_cost


@dataclass(frozen=True)
class Admission:
    scopes: dict[str, int]


async def admit(
    db: AsyncSession,
    settings: Settings,
    cache: Redis,
    token: str,
    request_id: UUID,
    protocol: Protocol,
    model: str,
    output: int,
) -> Admission:
    repo = GatewayRepository(db)
    await repo.lock()
    now = datetime.now(UTC)
    grant = await repo.authenticate(token, now)
    quotas = await repo.quotas(grant)
    route = next(
        (
            x
            for x in await repo.models(grant, quotas)
            if x.alias == model and x.protocol == protocol
        ),
        None,
    )
    if route is None:
        raise HTTPException(403, "Model is not allowed for this route")
    if (
        not settings.app_litellm_url
        or not settings.app_litellm_service_key
        or not settings.app_litellm_service_key.get_secret_value()
    ):
        raise HTTPException(503, "Model proxy is unavailable")
    # Operator-verified maximum total billable input per approved model alias.
    input_bound = settings.app_gateway_input_bounds.get(model)
    if input_bound is None:
        raise HTTPException(503, "No verified input ceiling for this model")
    price = await repo.price(route, "USD", now)
    reserved = upper_cost(price, input_bound, output)
    if reserved >= Decimal("1e18"):
        raise HTTPException(503, "Price configuration exceeds supported amount")

    record = GatewayRequest(
        id=request_id,
        key_id=grant.id,
        user_id=grant.owner_id,
        department_id=grant.department_id,
        project_id=grant.project_id,
        model_id=route.id,
        provider_id=route.provider_id,
        price_id=price.id,
        currency=price.currency,
        protocol=protocol,
        started_at=now,
        status="dispatching",
        settlement="reserved",
        reserved_cost=reserved,
    )
    scopes = {
        "enterprise": settings.app_gateway_rpm,
        f"department:{grant.department_id}": settings.app_gateway_rpm,
        f"project:{grant.project_id}": settings.app_gateway_rpm,
        f"user:{grant.owner_id}": settings.app_gateway_rpm,
        f"key:{grant.id}": settings.app_gateway_rpm,
    }
    warnings = []
    for rule in quotas:
        daily, monthly = await repo.exposure(rule, grant, now)
        if daily + reserved > rule.daily_amount or monthly + reserved > rule.monthly_amount:
            await reject(db, repo, record, "budget_denied")
            raise HTTPException(429, "Budget is insufficient")
        limits = ((daily, rule.daily_amount), (monthly, rule.monthly_amount))
        if any(
            current * 100 < limit * rule.warning_percent <= (current + reserved) * 100
            for current, limit in limits
        ):
            warnings.append(rule.id)
        target = getattr(rule, rule.scope + "_id", None)
        scope = rule.scope if target is None else f"{rule.scope}:{target}"
        scopes[scope] = min(scopes[scope], rule.rpm)

    try:
        await acquire(
            cache,
            request_id,
            scopes,
            input_bound + output,
            settings.app_gateway_deadline + 45,
            settings.app_gateway_tpm,
            settings.app_gateway_parallel,
        )
    except HTTPException as exc:
        await reject(
            db, repo, record, "rate_denied" if exc.status_code == 429 else "admission_unavailable"
        )
        raise
    try:
        db.add(record)
        key = await db.get(ApiKey, grant.id)
        if key is not None:
            key.last_used_at = now
        await db.flush()
        for quota_id in warnings:
            repo.event(request_id, "budget_warning", event_id=f"{request_id}:warning:{quota_id}")
        await db.commit()
    except BaseException:
        await release(cache, request_id, scopes)
        raise
    return Admission(scopes)


async def reject(
    db: AsyncSession, repo: GatewayRepository, record: GatewayRequest, status: str
) -> None:
    record.status, record.settlement, record.finished_at = status, "released", datetime.now(UTC)
    db.add(record)
    await db.flush()
    repo.event(record.id, status)
    await db.commit()


async def finalize(
    factory: async_sessionmaker,
    request_id: UUID,
    status: str,
    raw: dict,
    source: str,
    proxy_id: str | None = None,
    supplier_id: str | None = None,
    *,
    unbilled: bool = False,
    terminal: bool = True,
    event: UsageEvent | None = None,
) -> None:
    async with factory.begin() as db:
        repo = GatewayRepository(db)
        await repo.lock()
        row = await db.get(GatewayRequest, request_id, with_for_update=True)
        if row is None:
            raise HTTPException(404, "Unknown request")
        if event is not None:
            if event.proxy_call_id not in {row.proxy_call_id, request_id.hex}:
                raise HTTPException(409, "Proxy call ID mismatch")
            event_id = "callback:" + event.event_id
            fingerprint = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
            existing = await db.get(GatewayEvent, event_id)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise HTTPException(409, "Event ID conflict")
                return
            repo.event(request_id, "callback_received", fingerprint, event_id)
        row.proxy_call_id = row.proxy_call_id or proxy_id
        row.supplier_request_id = row.supplier_request_id or supplier_id
        if row.settlement in {"settled", "released"}:
            return
        raw = clean_usage(raw)
        normalized = normalize(row.protocol, raw) if terminal else None
        if raw:
            row.raw_usage, row.usage_source = raw, source
        if event is None or row.status == "dispatching":
            row.status = status
        row.finished_at = row.finished_at or datetime.now(UTC)
        if normalized is not None:
            price = await db.get(PriceVersion, row.price_id)
            if price is None:
                raise RuntimeError("Missing price snapshot")
            row.raw_usage, row.usage_source = raw, source
            row.normalized_usage = normalized
            row.platform_cost = cost(price, normalized)
            row.settlement = "settled"
            repo.event(request_id, "settled")
            if row.platform_cost > row.reserved_cost:
                repo.event(request_id, "reservation_exceeded")
        elif unbilled:
            row.settlement = "released"
            repo.event(request_id, "released")
        else:
            if row.settlement != "review":
                repo.event(request_id, "needs_review")
            row.settlement = "review"


async def reconcile_stale(factory: async_sessionmaker, seconds: int) -> int:
    async with factory() as db:
        stale = list(
            await db.scalars(
                select(GatewayRequest.id)
                .where(
                    GatewayRequest.settlement == "reserved",
                    GatewayRequest.started_at < datetime.now(UTC) - timedelta(seconds=seconds + 60),
                )
                .limit(100)
            )
        )
    for request_id in stale:
        await finalize(factory, request_id, "dispatch_unknown", {}, "recovery")
    return len(stale)

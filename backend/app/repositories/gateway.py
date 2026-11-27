from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import token_digest
from app.models.access import ApiKey, KeyGrant, KeyModel, QuotaModel, QuotaRule
from app.models.auth import UserAccount
from app.models.gateway import GatewayEvent, GatewayRequest
from app.models.model_catalog import ModelRoute, PriceVersion, Provider
from app.models.organization import Department
from app.models.project import Project, ProjectMember


class GatewayRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def lock(self) -> None:
        # Matches the transaction lock used by organization, key and price mutations.
        await self.db.execute(text("SELECT pg_advisory_xact_lock(63410021)"))

    async def authenticate(self, token: str, now: datetime) -> KeyGrant:
        if not token.startswith("tg_") or len(token) > 100:
            raise HTTPException(401, "Invalid API key")
        grant = await self.db.scalar(
            select(KeyGrant)
            .join(ApiKey, ApiKey.grant_id == KeyGrant.id)
            .join(UserAccount, UserAccount.id == KeyGrant.owner_id)
            .join(Department, Department.id == KeyGrant.department_id)
            .join(Project, Project.id == KeyGrant.project_id)
            .join(
                ProjectMember,
                and_(
                    ProjectMember.project_id == KeyGrant.project_id,
                    ProjectMember.user_id == KeyGrant.owner_id,
                    ProjectMember.department_id == KeyGrant.department_id,
                ),
            )
            .where(
                ApiKey.digest == token_digest(token),
                KeyGrant.state == "active",
                KeyGrant.expires_at > now,
                UserAccount.state == "active",
                UserAccount.primary_department_id == KeyGrant.department_id,
                Project.state == "active",
                Department.state == "active",
                ProjectMember.state == "active",
            )
        )
        if grant is None:
            raise HTTPException(401, "Invalid or inactive API key")
        return grant

    async def quotas(self, grant: KeyGrant) -> list[QuotaRule]:
        return list(
            await self.db.scalars(
                select(QuotaRule)
                .where(
                    or_(
                        QuotaRule.scope == "enterprise",
                        QuotaRule.key_id == grant.id,
                        QuotaRule.user_id == grant.owner_id,
                        QuotaRule.project_id == grant.project_id,
                        QuotaRule.department_id == grant.department_id,
                    )
                )
                .order_by(QuotaRule.id)
            )
        )

    async def models(self, grant: KeyGrant, quotas: list[QuotaRule]) -> list[ModelRoute]:
        query = (
            select(ModelRoute)
            .join(KeyModel)
            .join(Provider)
            .where(
                KeyModel.grant_id == grant.id,
                ModelRoute.state == "active",
                Provider.state == "active",
            )
        )
        for quota in quotas:
            allow = select(QuotaModel.model_id).where(QuotaModel.quota_id == quota.id)
            query = query.where(or_(~allow.exists(), ModelRoute.id.in_(allow)))
        return list(await self.db.scalars(query.order_by(ModelRoute.alias)))

    async def price(self, route: ModelRoute, currency: str, now: datetime) -> PriceVersion:
        price = await self.db.scalar(
            select(PriceVersion)
            .where(
                PriceVersion.model_route_id == route.id,
                PriceVersion.currency == currency,
                PriceVersion.effective_from <= now,
            )
            .order_by(PriceVersion.effective_from.desc())
            .limit(1)
        )
        if price is None:
            raise HTTPException(503, "No applicable price version")
        return price

    async def exposure(
        self, quota: QuotaRule, grant: KeyGrant, now: datetime
    ) -> tuple[Decimal, Decimal]:
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month = day.replace(day=1)
        charge = case(
            (GatewayRequest.settlement == "settled", GatewayRequest.platform_cost),
            (GatewayRequest.settlement.in_(["reserved", "review"]), GatewayRequest.reserved_cost),
            else_=0,
        )
        scopes = {
            "key": GatewayRequest.key_id == grant.id,
            "user": GatewayRequest.user_id == grant.owner_id,
            "department": GatewayRequest.department_id == grant.department_id,
            "project": GatewayRequest.project_id == grant.project_id,
        }
        query = select(
            func.coalesce(func.sum(charge).filter(GatewayRequest.started_at >= day), 0),
            func.coalesce(func.sum(charge), 0),
        ).where(
            GatewayRequest.started_at >= month,
            GatewayRequest.started_at <= now,
            GatewayRequest.currency == "USD",
        )
        if quota.scope in scopes:
            query = query.where(scopes[quota.scope])
        daily, monthly = (await self.db.execute(query)).one()
        return daily, monthly

    def event(
        self,
        request_id: UUID,
        kind: str,
        fingerprint: str | None = None,
        event_id: str | None = None,
    ) -> None:
        self.db.add(
            GatewayEvent(
                id=event_id or f"{request_id}:{kind}",
                request_id=request_id,
                kind=kind,
                fingerprint=fingerprint,
                created_at=datetime.now(UTC),
            )
        )

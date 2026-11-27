import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.models.access import ApiKey, KeyGrant, KeyModel, QuotaModel, QuotaRule
from app.models.auth import UserAccount
from app.models.model_catalog import ModelRoute, Provider
from app.models.organization import Department
from app.models.project import Project, ProjectMember
from app.repositories.access import AccessRepository
from app.schemas.access import KeyInput, KeyRecord, KeySecret, QuotaInput, QuotaRecord
from app.services.organization import OrganizationService

TARGETS = {
    "department": (Department, "department_id"),
    "project": (Project, "project_id"),
    "user": (UserAccount, "user_id"),
    "key": (KeyGrant, "key_id"),
}


class AccessService(OrganizationService):
    def __init__(
        self, repo: AccessRepository, request_id: str | None, *, gateway_configured: bool = False
    ) -> None:
        super().__init__(repo, request_id)
        self.access = repo
        self.gateway_status = "unknown" if gateway_configured else "unavailable"

    async def check_models(self, ids: list[UUID]) -> None:
        active = await self.db.scalars(
            select(ModelRoute.id)
            .join(Provider)
            .where(ModelRoute.id.in_(ids), ModelRoute.state == "active", Provider.state == "active")
        )
        if set(active) != set(ids):
            raise HTTPException(422, "Model allowlist contains an unavailable model")

    async def check_owner(self, owner_id: UUID, department_id: UUID, project_id: UUID) -> None:
        user = await self.require(UserAccount, owner_id)
        membership = await self.db.get(ProjectMember, (project_id, owner_id))
        if (
            user.state != "active"
            or user.primary_department_id != department_id
            or membership is None
            or membership.state != "active"
            or membership.department_id != department_id
        ):
            raise HTTPException(409, "Owner needs an active project membership in this department")
        await self.department(department_id)
        if (await self.require(Project, project_id)).state != "active":
            raise HTTPException(409, "Project is disabled")

    async def record_key(self, item: KeyGrant) -> KeyRecord:
        models = await self.db.scalars(
            select(KeyModel.model_id).where(KeyModel.grant_id == item.id)
        )
        key = await self.db.get(ApiKey, item.id)
        return KeyRecord(
            id=item.id,
            label=item.label,
            owner_id=item.owner_id,
            department_id=item.department_id,
            project_id=item.project_id,
            model_ids=list(models),
            expires_at=item.expires_at,
            state="expired"
            if item.state != "revoked" and item.expires_at <= datetime.now(UTC)
            else item.state,
            hint=key.hint if key else None,
            last_used_at=key.last_used_at if key else None,
            gateway_status=self.gateway_status,
        )

    async def grant(self, data: KeyInput) -> KeyRecord:
        await self.lock()
        if data.expires_at <= datetime.now(UTC):
            raise HTTPException(422, "Expiration must be in the future")
        await self.check_owner(data.owner_id, data.department_id, data.project_id)
        await self.check_models(data.model_ids)
        item = KeyGrant(**data.model_dump(exclude={"model_ids"}))
        self.db.add(item)
        await self.flush()
        self.db.add_all(
            KeyModel(grant_id=item.id, model_id=model_id) for model_id in set(data.model_ids)
        )
        await self.finish("key.granted", item.id, "key_grant", {"state": item.state})
        return await self.record_key(item)

    async def claim(self, target: UUID) -> KeySecret:
        await self.lock()
        item = await self.access.key(target, lock=True)
        if item is None or item.owner_id != self.access.actor.user_id:
            raise HTTPException(404, "Resource not found")
        if item.state != "pending" or item.expires_at <= datetime.now(UTC):
            raise HTTPException(409, "Key cannot be claimed")
        await self.check_owner(item.owner_id, item.department_id, item.project_id)
        await self.check_models((await self.record_key(item)).model_ids)
        secret = "tg_" + secrets.token_urlsafe(32)
        self.db.add(
            ApiKey(
                grant_id=item.id,
                digest=hashlib.sha256(secret.encode()).hexdigest(),
                hint=secret[:12],
            )
        )
        item.state = "active"
        await self.finish("key.claimed", item.id, "key_grant", {"state": item.state})
        return KeySecret(key=secret, gateway_status=self.gateway_status)

    async def change_key(self, target: UUID, state: str) -> KeyRecord:
        await self.lock()
        item = await self.access.key(target, lock=True)
        if item is None:
            raise HTTPException(404, "Resource not found")
        if state == item.state:
            return await self.record_key(item)
        valid = {
            "pending": {"revoked"},
            "active": {"paused", "revoked"},
            "paused": {"active", "revoked"},
            "revoked": set(),
        }
        if state not in valid[item.state] or (
            state != "revoked" and item.expires_at <= datetime.now(UTC)
        ):
            raise HTTPException(409, "Key cannot change to this state")
        if state == "active":
            await self.check_owner(item.owner_id, item.department_id, item.project_id)
            await self.check_models((await self.record_key(item)).model_ids)
        item.state = state
        await self.finish("key." + state, item.id, "key_grant", {"state": item.state})
        return await self.record_key(item)

    async def record_quota(self, item: QuotaRule) -> QuotaRecord:
        models = await self.db.scalars(
            select(QuotaModel.model_id).where(QuotaModel.quota_id == item.id)
        )
        target = getattr(item, TARGETS[item.scope][1]) if item.scope in TARGETS else None
        return QuotaRecord(
            id=item.id,
            scope=item.scope,
            target_id=target,
            daily_amount=item.daily_amount,
            monthly_amount=item.monthly_amount,
            rpm=item.rpm,
            warning_percent=item.warning_percent,
            model_ids=list(models),
        )

    async def save_quota(self, data: QuotaInput, target: UUID | None = None) -> QuotaRecord:
        await self.lock()
        await self.check_models(data.model_ids)
        values = data.model_dump(exclude={"target_id", "model_ids"})
        if data.target_id is not None:
            model, column = TARGETS[data.scope]
            await self.require(model, data.target_id)
            values[column] = data.target_id
        if target is None:
            item = QuotaRule(**values)
            self.db.add(item)
            await self.flush()
        else:
            item = await self.require(QuotaRule, target)
            existing = await self.record_quota(item)
            if (existing.scope, existing.target_id) != (data.scope, data.target_id):
                raise HTTPException(409, "Quota scope is immutable")
            for name, value in values.items():
                setattr(item, name, value)
            await self.db.execute(delete(QuotaModel).where(QuotaModel.quota_id == item.id))
        self.db.add_all(
            QuotaModel(quota_id=item.id, model_id=model_id) for model_id in set(data.model_ids)
        )
        await self.finish(
            "quota.saved",
            item.id,
            "quota_rule",
            {"scope": data.scope, "fields": sorted(data.model_fields_set)},
        )
        return await self.record_quota(item)

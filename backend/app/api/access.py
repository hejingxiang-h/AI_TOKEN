from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.api.auth import Database
from app.api.organization import PageNumber, PageSize, Search, require
from app.api.permissions import Actor, Administrator
from app.models.access import KeyGrant, QuotaRule
from app.repositories.access import AccessRepository
from app.schemas.access import KeyInput, KeyRecord, KeySecret, KeyState, QuotaInput, QuotaRecord
from app.schemas.organization import Page
from app.services.access import AccessService

router = APIRouter(prefix="/api/v1", tags=["keys and quotas"])


def access_service(db: Database, actor: Actor, request: Request) -> AccessService:
    config = request.app.state.settings
    key = config.app_litellm_service_key
    available = bool(config.app_litellm_url and key and key.get_secret_value())
    return AccessService(
        AccessRepository(db, actor),
        getattr(request.state, "request_id", None),
        gateway_configured=available,
    )


Access = Annotated[AccessService, Depends(access_service)]


@router.get("/keys")
async def keys(
    service: Access, page: PageNumber = 1, size: PageSize = 20, q: Search = ""
) -> Page[KeyRecord]:
    rows, total = await service.access.read_page(
        service.access.keys()
        .where(KeyGrant.label.icontains(q, autoescape=True))
        .order_by(KeyGrant.created_at.desc(), KeyGrant.id),
        page,
        size,
    )
    return Page(items=[await service.record_key(row) for row in rows], total=total)


@router.get("/keys/{target}")
async def key(target: UUID, service: Access) -> KeyRecord:
    return await service.record_key(require(await service.access.key(target)))


@router.post("/keys/grants", status_code=201)
async def grant(data: KeyInput, service: Access, _admin: Administrator) -> KeyRecord:
    return await service.grant(data)


@router.post("/keys/{target}/claim", status_code=201)
async def claim(target: UUID, response: Response, service: Access) -> KeySecret:
    response.headers["Cache-Control"] = "no-store"
    return await service.claim(target)


@router.patch("/keys/{target}")
async def change_key(
    target: UUID, data: KeyState, service: Access, _admin: Administrator
) -> KeyRecord:
    return await service.change_key(target, data.state)


@router.get("/quotas")
async def quotas(
    service: Access, page: PageNumber = 1, size: PageSize = 20, q: Search = ""
) -> Page[QuotaRecord]:
    rows, total = await service.access.read_page(
        service.access.quotas()
        .where(QuotaRule.scope.icontains(q, autoescape=True))
        .order_by(QuotaRule.scope, QuotaRule.id),
        page,
        size,
    )
    return Page(items=[await service.record_quota(row) for row in rows], total=total)


@router.get("/quotas/{target}")
async def quota(target: UUID, service: Access) -> QuotaRecord:
    return await service.record_quota(
        require(await service.db.scalar(service.access.quotas().where(QuotaRule.id == target)))
    )


@router.post("/quotas", status_code=201)
async def create_quota(data: QuotaInput, service: Access, _admin: Administrator) -> QuotaRecord:
    return await service.save_quota(data)


@router.put("/quotas/{target}")
async def update_quota(
    target: UUID, data: QuotaInput, service: Access, _admin: Administrator
) -> QuotaRecord:
    return await service.save_quota(data, target)

from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.organization import Management, PageNumber, PageSize, Search
from app.integrations.litellm import LiteLLM
from app.models.model_catalog import ModelRoute, PriceVersion, Provider
from app.schemas.model_catalog import (
    ModelInput,
    ModelRecord,
    PriceInput,
    PriceRecord,
    ProbeResult,
    ProviderInput,
    ProviderRecord,
    StatePatch,
)
from app.schemas.organization import Page
from app.services.model_catalog import CatalogService

router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/providers")
async def providers(manager: Management) -> list[ProviderRecord]:
    items = await manager.db.scalars(select(Provider).order_by(Provider.code))
    return [ProviderRecord.model_validate(item) for item in items]


@router.post("/providers", status_code=201)
async def create_provider(data: ProviderInput, manager: Management) -> ProviderRecord:
    return ProviderRecord.model_validate(await CatalogService(manager).create_provider(data))


@router.patch("/providers/{target}")
async def provider_state(target: UUID, data: StatePatch, manager: Management) -> ProviderRecord:
    return ProviderRecord.model_validate(
        await CatalogService(manager).state(Provider, target, data.state)
    )


@router.get("/model-routes")
async def models(
    manager: Management, page: PageNumber = 1, size: PageSize = 20, q: Search = ""
) -> Page[ModelRecord]:
    items, total = await manager.repo.read_page(
        select(ModelRoute)
        .where(ModelRoute.alias.icontains(q, autoescape=True))
        .order_by(ModelRoute.alias),
        page,
        size,
    )
    return Page(items=[ModelRecord.model_validate(item) for item in items], total=total)


@router.get("/model-routes/{target}")
async def model(target: UUID, manager: Management) -> ModelRecord:
    return ModelRecord.model_validate(await manager.require(ModelRoute, target))


@router.post("/model-routes", status_code=201)
async def create_model(data: ModelInput, manager: Management) -> ModelRecord:
    return ModelRecord.model_validate(await CatalogService(manager).create_model(data))


@router.patch("/model-routes/{target}")
async def model_state(target: UUID, data: StatePatch, manager: Management) -> ModelRecord:
    return ModelRecord.model_validate(
        await CatalogService(manager).state(ModelRoute, target, data.state)
    )


@router.get("/model-routes/{target}/prices")
async def prices(
    target: UUID, manager: Management, page: PageNumber = 1, size: PageSize = 20
) -> Page[PriceRecord]:
    await manager.require(ModelRoute, target)
    rows, total = await manager.repo.read_page(
        select(PriceVersion)
        .where(PriceVersion.model_route_id == target)
        .order_by(PriceVersion.effective_from.desc(), PriceVersion.id),
        page,
        size,
    )
    return Page(
        items=[PriceRecord.model_validate(row, from_attributes=True) for row in rows], total=total
    )


@router.post("/model-routes/{target}/prices", status_code=201)
async def add_price(target: UUID, data: PriceInput, manager: Management) -> PriceRecord:
    return PriceRecord.model_validate(
        await CatalogService(manager).price(target, data), from_attributes=True
    )


@router.post("/model-routes/{target}/probe")
async def probe(target: UUID, manager: Management, request: Request) -> ProbeResult:
    return await CatalogService(manager).probe(target, LiteLLM(request.app.state.settings))

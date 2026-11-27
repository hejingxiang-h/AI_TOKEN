from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.integrations.litellm import LiteLLM
from app.models.model_catalog import ModelRoute, PriceVersion, Provider
from app.schemas.model_catalog import ModelInput, PriceInput, ProbeResult, ProviderInput
from app.services.organization import OrganizationService


class CatalogService:
    def __init__(self, manager: OrganizationService) -> None:
        self.manager = manager
        self.db = manager.db

    async def create_provider(self, data: ProviderInput) -> Provider:
        item = Provider(code=data.code.lower(), state=data.state)
        self.db.add(item)
        await self.manager.flush()
        await self.manager.finish("provider.created", item.id, "provider")
        return item

    async def create_model(self, data: ModelInput) -> ModelRoute:
        await self.manager.require(Provider, data.provider_id)
        item = ModelRoute(**data.model_dump())
        self.db.add(item)
        await self.manager.flush()
        await self.manager.finish("model.created", item.id, "model_route")
        return item

    async def state[T: (Provider, ModelRoute)](self, model: type[T], target: UUID, state: str) -> T:
        item = await self.manager.require(model, target)
        item.state = state
        await self.manager.finish("catalog.state_updated", item.id, item.__tablename__)
        return item

    async def price(self, target: UUID, data: PriceInput) -> PriceVersion:
        await self.manager.lock()
        await self.manager.require(ModelRoute, target)
        newest = await self.db.scalar(
            select(PriceVersion.effective_from)
            .where(
                PriceVersion.model_route_id == target,
                PriceVersion.currency == data.currency,
            )
            .order_by(PriceVersion.effective_from.desc())
            .limit(1)
        )
        if newest and data.effective_from <= newest:
            raise HTTPException(409, "Price effective times must increase per currency")
        item = PriceVersion(model_route_id=target, **data.model_dump())
        self.db.add(item)
        await self.manager.flush()
        await self.manager.finish("price.created", item.id, "price_version")
        return item

    async def probe(self, target: UUID, client: LiteLLM) -> ProbeResult:
        item = await self.manager.require(ModelRoute, target)
        provider = await self.manager.require(Provider, item.provider_id)
        if provider.state != "active" or item.state != "active":
            raise HTTPException(409, "Model or provider is disabled")
        try:
            result = await client.request("GET", "/health", params={"model": item.alias})
            healthy = result.get("healthy_endpoints")
            unhealthy = result.get("unhealthy_endpoints")
            status = "healthy" if healthy and not unhealthy else "unhealthy"
        except HTTPException:
            status = "unavailable"
        await self.manager.finish("model.probed_" + status, item.id, "model_route")
        return ProbeResult(status=status)

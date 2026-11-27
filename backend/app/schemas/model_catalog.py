from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.organization import Code, Input, Label, Record, State

Money = Annotated[Decimal, Field(ge=0, max_digits=30, decimal_places=12)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Protocol = Literal["chat_completions", "messages", "responses"]


class ProviderInput(Input):
    code: Code
    state: State = "active"


class StatePatch(Input):
    state: State


class ProviderRecord(Record):
    code: str


class ModelInput(Input):
    provider_id: UUID
    alias: Label
    upstream_model: Label
    protocol: Protocol
    state: State = "active"


class ModelRecord(Record):
    provider_id: UUID
    alias: str
    upstream_model: str
    protocol: Protocol


class PriceInput(Input):
    currency: Currency
    effective_from: AwareDatetime
    unit_tokens: int = Field(default=1000000, ge=1, le=1000000000)
    input_price: Money
    output_price: Money
    cache_read_price: Money | None = None
    cache_write_price: Money | None = None
    source_ref: str = Field(min_length=1, max_length=240)


class PriceRecord(PriceInput):
    id: UUID
    model_route_id: UUID


class ProbeResult(BaseModel):
    status: Literal["healthy", "unhealthy", "unavailable"]

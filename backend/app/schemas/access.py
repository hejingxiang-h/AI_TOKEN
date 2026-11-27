from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

ModelIDs = Annotated[list[UUID], Field(max_length=100)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=30, decimal_places=12)]


class KeyInput(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    owner_id: UUID
    department_id: UUID
    project_id: UUID
    model_ids: ModelIDs = Field(min_length=1)
    expires_at: AwareDatetime


class KeyState(BaseModel):
    state: Literal["paused", "active", "revoked"]


class KeyRecord(KeyInput):
    id: UUID
    state: str
    hint: str | None
    last_used_at: datetime | None
    gateway_status: Literal["unavailable", "unknown"] = "unknown"


class KeySecret(BaseModel):
    key: str
    gateway_status: Literal["unavailable", "unknown"] = "unknown"


class QuotaInput(BaseModel):
    scope: Literal["enterprise", "department", "project", "user", "key"]
    target_id: UUID | None = None
    daily_amount: Amount
    monthly_amount: Amount
    rpm: int = Field(gt=0, le=2147483647)
    warning_percent: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    model_ids: ModelIDs = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rule(self) -> "QuotaInput":
        if (self.target_id is None) != (self.scope == "enterprise"):
            raise ValueError("Scope requires a matching target")
        if self.monthly_amount < self.daily_amount:
            raise ValueError("Monthly limit must cover daily limit")
        return self


class QuotaRecord(QuotaInput):
    id: UUID
    currency: Literal["USD"] = "USD"

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Preset = Literal["today", "yesterday", "7d", "30d", "month", "custom"]
Dimension = Literal["department", "project", "user", "model", "provider", "key"]


class UsageQuery(BaseModel):
    period: Preset = "today"
    start: date | None = None
    end: date | None = None
    user_id: UUID | None = None
    department_id: UUID | None = None
    project_id: UUID | None = None
    key_id: UUID | None = None
    provider_id: UUID | None = None
    model_id: UUID | None = None


class UsageRange(BaseModel):
    timezone: str
    start: date
    end: date
    start_at: datetime
    end_at: datetime


class Metrics(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    cache_tokens: int | None
    total_tokens: int | None
    calls: int
    successes: int
    failures: int
    in_progress: int
    active_users: int
    active_keys: int
    average_response_ms: Decimal | None
    unsettled: int
    unknown_usage: int
    costs: dict[str, Decimal]
    success_rate: Decimal | None


class Summary(BaseModel):
    window: UsageRange
    metrics: Metrics


class Group(BaseModel):
    id: str
    label: str
    metrics: Metrics


class Breakdown(BaseModel):
    window: UsageRange
    items: list[Group]


class UsageRecord(BaseModel):
    id: UUID
    user_id: UUID
    department_id: UUID
    project_id: UUID
    key_id: UUID
    model_id: UUID
    provider_id: UUID
    price_id: UUID
    currency: str
    protocol: str
    client_type: str | None
    risk_state: str
    duration_ms: float | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    settlement: str
    normalized_usage: dict[str, int] | None
    usage_source: str | None
    platform_cost: Decimal | None
    model: str
    provider: str


class UsageDetail(UsageRecord):
    source_ip: str | None
    raw_usage: dict | None
    supplier_request_id: str | None
    proxy_call_id: str | None
    supplier_cost: Decimal | None


class RecordPage(BaseModel):
    window: UsageRange
    items: list[UsageRecord]
    total: int

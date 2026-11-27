from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GatewayRequest(Base):
    __tablename__ = "gateway_request"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    key_id: Mapped[UUID] = mapped_column(ForeignKey("api_key.grant_id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    department_id: Mapped[UUID] = mapped_column(ForeignKey("department.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("project.id"), index=True)
    model_id: Mapped[UUID] = mapped_column(ForeignKey("model_route.id"))
    provider_id: Mapped[UUID] = mapped_column(ForeignKey("provider.id"))
    price_id: Mapped[UUID] = mapped_column(ForeignKey("price_version.id"))
    currency: Mapped[str] = mapped_column(String(3))
    protocol: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24))
    settlement: Mapped[str] = mapped_column(String(24), index=True)
    proxy_call_id: Mapped[str | None] = mapped_column(String(160))
    supplier_request_id: Mapped[str | None] = mapped_column(String(160))
    normalized_usage: Mapped[dict | None] = mapped_column(JSONB)
    raw_usage: Mapped[dict | None] = mapped_column(JSONB)
    usage_source: Mapped[str | None] = mapped_column(String(24))
    reserved_cost: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    platform_cost: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    supplier_cost: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))


class GatewayEvent(Base):
    __tablename__ = "gateway_event"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("gateway_request.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

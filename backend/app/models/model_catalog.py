from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Provider(Base):
    __tablename__ = "provider"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(16), default="active")


class ModelRoute(Base):
    __tablename__ = "model_route"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(ForeignKey("provider.id"), index=True)
    alias: Mapped[str] = mapped_column(String(120), unique=True)
    upstream_model: Mapped[str] = mapped_column(String(120))
    protocol: Mapped[str] = mapped_column(String(24))
    state: Mapped[str] = mapped_column(String(16), default="active")


class PriceVersion(Base):
    __tablename__ = "price_version"
    __table_args__ = (
        UniqueConstraint("model_route_id", "currency", "effective_from", name="uq_price_start"),
        CheckConstraint(
            "input_price >= 0 AND output_price >= 0 AND unit_tokens > 0", name="ck_price_amount"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    model_route_id: Mapped[UUID] = mapped_column(ForeignKey("model_route.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    unit_tokens: Mapped[int]
    input_price: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    output_price: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    cache_read_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    cache_write_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    source_ref: Mapped[str] = mapped_column(String(240))

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiskAlert(Base):
    __tablename__ = "risk_alert"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    fingerprint: Mapped[str] = mapped_column(String(180), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    severity: Mapped[str] = mapped_column(String(12))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[UUID | None]
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("user_account.id"), index=True)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("department.id"), index=True)
    evidence: Mapped[dict] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("user_account.id"))


class RiskSignal(Base):
    __tablename__ = "risk_signal"
    __table_args__ = (Index("ix_risk_signal_minute", "minute"),)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    minute: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int]

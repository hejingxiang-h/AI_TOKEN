from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KeyGrant(Base):
    __tablename__ = "key_grant"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    department_id: Mapped[UUID] = mapped_column(ForeignKey("department.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("project.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KeyModel(Base):
    __tablename__ = "key_model"
    grant_id: Mapped[UUID] = mapped_column(ForeignKey("key_grant.id"), primary_key=True)
    model_id: Mapped[UUID] = mapped_column(ForeignKey("model_route.id"), primary_key=True)


class ApiKey(Base):
    __tablename__ = "api_key"
    grant_id: Mapped[UUID] = mapped_column(ForeignKey("key_grant.id"), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    hint: Mapped[str] = mapped_column(String(16))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuotaRule(Base):
    __tablename__ = "quota_rule"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('enterprise','department','project','user','key') AND "
            "num_nonnulls(department_id, project_id, user_id, key_id) = "
            "CASE WHEN scope = 'enterprise' THEN 0 ELSE 1 END AND "
            "(scope <> 'department' OR department_id IS NOT NULL) AND "
            "(scope <> 'project' OR project_id IS NOT NULL) AND "
            "(scope <> 'user' OR user_id IS NOT NULL) AND "
            "(scope <> 'key' OR key_id IS NOT NULL)",
            name="ck_quota_scope",
        ),
        CheckConstraint(
            "daily_amount > 0 AND monthly_amount >= daily_amount AND rpm > 0 "
            "AND warning_percent > 0 AND warning_percent <= 100",
            name="ck_quota_limits",
        ),
        Index(
            "uq_quota_scope",
            "scope",
            "department_id",
            "project_id",
            "user_id",
            "key_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(16))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("department.id"))
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("project.id"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("user_account.id"))
    key_id: Mapped[UUID | None] = mapped_column(ForeignKey("key_grant.id"))
    daily_amount: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    monthly_amount: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    rpm: Mapped[int]
    warning_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class QuotaModel(Base):
    __tablename__ = "quota_model"
    quota_id: Mapped[UUID] = mapped_column(ForeignKey("quota_rule.id"), primary_key=True)
    model_id: Mapped[UUID] = mapped_column(ForeignKey("model_route.id"), primary_key=True)

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Role(StrEnum):
    USER = "USER"
    DEPARTMENT_MANAGER = "DEPARTMENT_MANAGER"
    SUPER_ADMIN = "SUPER_ADMIN"


class Department(Base):
    __tablename__ = "department"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("department.id"), index=True)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("user_account.id"))
    state: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = (
        CheckConstraint(
            "role_code IN ('USER','DEPARTMENT_MANAGER','SUPER_ADMIN')", name="ck_user_role_code"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("user_account.id"), primary_key=True)
    role_code: Mapped[str] = mapped_column(String(24))


class DepartmentGrant(Base):
    __tablename__ = "department_grant"

    supervisor_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_account.id"), primary_key=True
    )
    department_id: Mapped[UUID] = mapped_column(ForeignKey("department.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), default="active")

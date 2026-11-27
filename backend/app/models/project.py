from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Project(Base):
    __tablename__ = "project"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectDepartment(Base):
    __tablename__ = "project_department"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("project.id"), primary_key=True)
    department_id: Mapped[UUID] = mapped_column(ForeignKey("department.id"), primary_key=True)


class ProjectMember(Base):
    __tablename__ = "project_member"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "department_id"],
            ["project_department.project_id", "project_department.department_id"],
        ),
    )

    project_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user_account.id"), primary_key=True)
    department_id: Mapped[UUID]
    state: Mapped[str] = mapped_column(String(16), default="active")

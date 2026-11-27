from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import ColumnElement, false, or_, true
from sqlalchemy.orm import InstrumentedAttribute

from app.models.organization import Role


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: Role
    department_ids: frozenset[UUID]

    def within(
        self, owner: InstrumentedAttribute, department: InstrumentedAttribute | None = None
    ) -> ColumnElement[bool]:
        if self.role == Role.SUPER_ADMIN:
            return true()
        own = owner == self.user_id
        if self.role == Role.DEPARTMENT_MANAGER and department is not None:
            return or_(own, department.in_(self.department_ids))
        return own

    def department_scope(self, department: InstrumentedAttribute) -> ColumnElement[bool]:
        if self.role == Role.SUPER_ADMIN:
            return true()
        return department.in_(self.department_ids) if self.department_ids else false()

    def require_admin(self) -> None:
        if self.role != Role.SUPER_ADMIN:
            raise HTTPException(403, "Administrator privileges required")

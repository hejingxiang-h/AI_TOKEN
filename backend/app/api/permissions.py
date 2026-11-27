from typing import Annotated

from fastapi import Depends
from sqlalchemy import select

from app.api.auth import Database, Identity
from app.core.permissions import Principal
from app.models.organization import Department, DepartmentGrant, Role, UserRole


async def get_principal(identity: Identity, db: Database) -> Principal:
    user = identity[0]
    assignment = await db.get(UserRole, user.id)
    role = Role(assignment.role_code) if assignment else Role.USER
    departments = frozenset()
    if role == Role.DEPARTMENT_MANAGER:
        departments = frozenset(
            await db.scalars(
                select(DepartmentGrant.department_id)
                .join(Department, Department.id == DepartmentGrant.department_id)
                .where(
                    DepartmentGrant.supervisor_user_id == user.id,
                    DepartmentGrant.state == "active",
                    Department.state == "active",
                )
            )
        )
    return Principal(user.id, role, departments)


Actor = Annotated[Principal, Depends(get_principal)]


def require_admin(actor: Actor) -> Principal:
    actor.require_admin()
    return actor


Administrator = Annotated[Principal, Depends(require_admin)]

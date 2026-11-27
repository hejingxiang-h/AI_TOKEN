from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import ColumnElement
from sqlalchemy.dialects import postgresql

from app.core.permissions import Principal
from app.models.auth import UserAccount
from app.models.organization import Department, Role


def test_scope_filters_and_admin_action() -> None:
    owner, department = uuid4(), uuid4()
    employee = Principal(owner, Role.USER, frozenset())
    manager = Principal(owner, Role.DEPARTMENT_MANAGER, frozenset({department}))
    admin = Principal(owner, Role.SUPER_ADMIN, frozenset())
    for actor in (employee, manager):
        with pytest.raises(HTTPException) as exc:
            actor.require_admin()
        assert exc.value.status_code == 403
    admin.require_admin()

    def compile_scope(expression: ColumnElement[bool]) -> str:
        return str(
            expression.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )

    assert str(owner) in compile_scope(employee.within(UserAccount.id))
    assert compile_scope(employee.department_scope(Department.id)) == "false"
    assert str(department) in compile_scope(manager.department_scope(Department.id))
    assert compile_scope(admin.within(UserAccount.id)) == "true"

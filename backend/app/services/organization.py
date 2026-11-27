from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.auth import hash_password
from app.models.auth import UserAccount
from app.models.organization import Department, DepartmentGrant, Role, UserRole
from app.models.project import Project, ProjectDepartment, ProjectMember
from app.repositories.auth import AuthRepository
from app.repositories.organization import OrganizationRepository
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentPatch,
    ProjectCreate,
    ProjectMembership,
    ProjectPatch,
    UserCreate,
    UserPatch,
)


class OrganizationService:
    def __init__(self, repo: OrganizationRepository, request_id: str | None) -> None:
        self.repo = repo
        self.db = repo.db
        self.auth = AuthRepository(self.db)
        self.request_id = request_id

    async def lock(self) -> None:
        await self.db.execute(text("SELECT pg_advisory_xact_lock(63410021)"))

    async def require[T](self, model: type[T], target_id: UUID) -> T:
        item = await self.db.get(model, target_id)
        if item is None:
            raise HTTPException(404, "Resource not found")
        return item

    async def department(self, identifier: UUID | None) -> None:
        if identifier and (await self.require(Department, identifier)).state != "active":
            raise HTTPException(409, "Department is disabled")

    async def flush(self) -> None:
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(409, "Resource conflicts with existing data") from exc

    async def finish(self, action: str, target: UUID, target_type: str) -> None:
        self.auth.audit(
            self.repo.actor.user_id, action, target, self.request_id, target_type=target_type
        )
        await self.flush()
        await self.db.commit()

    async def create_user(self, data: UserCreate) -> UserAccount:
        login = data.login.casefold()
        if len(login) > 254:
            raise HTTPException(422, "Normalized login is too long")
        digest = await hash_password(data.password.get_secret_value())
        await self.lock()
        await self.department(data.primary_department_id)
        item = UserAccount(
            login_normalized=login,
            display_name=data.display_name,
            password_hash=digest,
            primary_department_id=data.primary_department_id,
        )
        self.db.add(item)
        await self.flush()
        self.db.add(UserRole(user_id=item.id, role_code=data.role))
        await self.finish("user.created", item.id, "user_account")
        return item

    async def patch_user(self, target: UUID, data: UserPatch) -> UserAccount:
        await self.lock()
        item = await self.auth.user(target, lock=True)
        if item is None:
            raise HTTPException(404, "Resource not found")
        role = await self.db.get(UserRole, target)
        current_role = Role(role.role_code) if role else Role.USER
        if (
            current_role == Role.SUPER_ADMIN
            and item.state == "active"
            and (data.state == "disabled" or data.role not in (None, Role.SUPER_ADMIN))
        ):
            count = await self.db.scalar(
                select(func.count())
                .select_from(UserRole)
                .join(UserAccount, UserAccount.id == UserRole.user_id)
                .where(UserRole.role_code == Role.SUPER_ADMIN, UserAccount.state == "active")
            )
            if count <= 1:
                raise HTTPException(409, "At least one active administrator is required")
        changed = False
        if data.display_name is not None:
            item.display_name = data.display_name
        if "primary_department_id" in data.model_fields_set:
            await self.department(data.primary_department_id)
            changed |= item.primary_department_id != data.primary_department_id
            item.primary_department_id = data.primary_department_id
        if data.state is not None:
            changed |= item.state != data.state
            item.state = data.state
        if data.role is not None and current_role != data.role:
            changed = True
            if role is None:
                self.db.add(UserRole(user_id=target, role_code=data.role))
            else:
                role.role_code = data.role
        if changed:
            item.auth_epoch += 1
            await self.auth.revoke_sessions(item.id, datetime.now(UTC))
        await self.finish("user.updated", target, "user_account")
        return item

    async def department_change(
        self, data: DepartmentCreate | DepartmentPatch, target: UUID | None = None
    ) -> Department:
        await self.lock()
        item = await self.require(Department, target) if target else Department()
        if isinstance(data, DepartmentCreate):
            item.code = data.code
        for name, value in data.model_dump(exclude_unset=target is not None).items():
            if name in ("name", "state") and value is None:
                continue
            if name == "owner_id" and value:
                if (await self.require(UserAccount, value)).state != "active":
                    raise HTTPException(409, "Department owner is disabled")
            if name == "parent_id" and value:
                await self.department(value)
                chain = {target}
                parent = value
                while parent:
                    if parent in chain:
                        raise HTTPException(409, "Department hierarchy contains a cycle")
                    chain.add(parent)
                    parent = (await self.require(Department, parent)).parent_id
            setattr(item, name, value)
        self.db.add(item)
        await self.flush()
        await self.finish(
            "department.updated" if target else "department.created", item.id, "department"
        )
        return item

    async def grant(self, department: UUID, user: UUID, state: str) -> None:
        await self.lock()
        await self.department(department)
        await self.require(UserAccount, user)
        role = await self.db.get(UserRole, user)
        if state == "active" and (role is None or role.role_code != Role.DEPARTMENT_MANAGER):
            raise HTTPException(409, "User is not a department manager")
        record = await self.db.get(DepartmentGrant, (user, department))
        if record is None:
            self.db.add(
                DepartmentGrant(supervisor_user_id=user, department_id=department, state=state)
            )
        else:
            record.state = state
        await self.finish("department.scope_updated", department, "department")

    async def project_change(
        self, data: ProjectCreate | ProjectPatch, target: UUID | None = None
    ) -> Project:
        await self.lock()
        item = await self.require(Project, target) if target else Project()
        for name, value in data.model_dump(exclude_unset=target is not None).items():
            if value is not None:
                setattr(item, name, value)
        self.db.add(item)
        await self.flush()
        await self.finish("project.updated" if target else "project.created", item.id, "project")
        return item

    async def project_member(
        self, project_id: UUID, user_id: UUID, data: ProjectMembership
    ) -> None:
        await self.lock()
        project = await self.require(Project, project_id)
        user = await self.require(UserAccount, user_id)
        membership = await self.db.get(ProjectMember, (project_id, user_id))
        if data.state == "disabled":
            if membership is None:
                raise HTTPException(404, "Membership not found")
            membership.state = "disabled"
        else:
            await self.department(data.department_id)
            if (
                user.primary_department_id != data.department_id
                or user.state != "active"
                or project.state != "active"
            ):
                raise HTTPException(409, "User or project is ineligible")
            if await self.db.get(ProjectDepartment, (project_id, data.department_id)) is None:
                self.db.add(
                    ProjectDepartment(project_id=project_id, department_id=data.department_id)
                )
                await self.flush()
            if membership is None:
                self.db.add(
                    ProjectMember(
                        project_id=project_id,
                        user_id=user_id,
                        department_id=data.department_id,
                        state="active",
                    )
                )
            else:
                membership.department_id = data.department_id
                membership.state = "active"
        await self.finish("project.membership_updated", project_id, "project")

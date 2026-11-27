from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Principal
from app.models.auth import UserAccount
from app.models.organization import Department, Role, UserRole
from app.models.project import Project, ProjectDepartment, ProjectMember
from app.schemas.organization import UserRecord


class OrganizationRepository:
    def __init__(self, db: AsyncSession, actor: Principal) -> None:
        self.db = db
        self.actor = actor

    def users(self) -> Select:
        return select(UserAccount).where(
            self.actor.within(UserAccount.id, UserAccount.primary_department_id)
        )

    def departments(self) -> Select:
        mine = select(UserAccount.primary_department_id).where(UserAccount.id == self.actor.user_id)
        return select(Department).where(
            or_(self.actor.department_scope(Department.id), Department.id.in_(mine))
        )

    def projects(self) -> Select:
        own = exists().where(
            ProjectMember.project_id == Project.id,
            ProjectMember.user_id == self.actor.user_id,
            ProjectMember.state == "active",
        )
        scoped = exists().where(
            ProjectDepartment.project_id == Project.id,
            ProjectDepartment.department_id.in_(self.actor.department_ids),
        )
        return select(Project).where(
            true() if self.actor.role == Role.SUPER_ADMIN else or_(own, scoped)
        )

    async def read_page[T](self, query: Select, page: int, size: int) -> tuple[list[T], int]:
        total = await self.db.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        items = await self.db.scalars(query.offset((page - 1) * size).limit(size))
        return list(items), total or 0

    async def users_output(self, users: list[UserAccount]) -> list[UserRecord]:
        roles = dict(
            (
                await self.db.execute(
                    select(UserRole.user_id, UserRole.role_code).where(
                        UserRole.user_id.in_([u.id for u in users])
                    )
                )
            )
            .tuples()
            .all()
        )
        return [
            UserRecord(
                id=u.id,
                login_normalized=u.login_normalized,
                display_name=u.display_name,
                state=u.state,
                primary_department_id=u.primary_department_id,
                role=Role(roles.get(u.id, Role.USER)),
            )
            for u in users
        ]

    async def scoped_members(self, project_id: UUID) -> list[ProjectMember]:
        return list(
            await self.db.scalars(
                select(ProjectMember)
                .where(
                    ProjectMember.project_id == project_id,
                    self.actor.within(ProjectMember.user_id, ProjectMember.department_id),
                )
                .order_by(ProjectMember.user_id)
            )
        )

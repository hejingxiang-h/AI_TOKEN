from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.auth import Database
from app.api.permissions import Actor, Administrator
from app.models.auth import UserAccount
from app.models.organization import Department, Role
from app.models.project import Project
from app.repositories.organization import OrganizationRepository
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentPatch,
    DepartmentRecord,
    GrantInput,
    MemberRecord,
    Page,
    ProjectCreate,
    ProjectMembership,
    ProjectPatch,
    ProjectRecord,
    UserCreate,
    UserPatch,
    UserRecord,
)
from app.services.organization import OrganizationService

router = APIRouter(prefix="/api/v1", tags=["organization"])
PageNumber = Annotated[int, Query(ge=1, le=100000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str, Query(max_length=120)]


def repository(db: Database, actor: Actor) -> OrganizationRepository:
    return OrganizationRepository(db, actor)


Repo = Annotated[OrganizationRepository, Depends(repository)]


def management(request: Request, db: Database, actor: Administrator) -> OrganizationService:
    return OrganizationService(
        OrganizationRepository(db, actor), getattr(request.state, "request_id", None)
    )


Management = Annotated[OrganizationService, Depends(management)]


def require[T](value: T | None) -> T:
    if value is None:
        raise HTTPException(404, "Resource not found")
    return value


@router.get("/roles")
async def roles(_admin: Administrator) -> list[Role]:
    return list(Role)


@router.get("/users")
async def list_users(
    repo: Repo,
    page: PageNumber = 1,
    size: PageSize = 20,
    q: Search = "",
    department_id: UUID | None = None,
) -> Page[UserRecord]:
    query = repo.users().where(UserAccount.display_name.icontains(q, autoescape=True))
    if department_id is not None:
        query = query.where(UserAccount.primary_department_id == department_id)
    items, total = await repo.read_page(
        query.order_by(UserAccount.display_name, UserAccount.id), page, size
    )
    return Page(items=await repo.users_output(items), total=total)


@router.get("/users/{target}")
async def get_user(target: UUID, repo: Repo) -> UserRecord:
    item = require(await repo.db.scalar(repo.users().where(UserAccount.id == target)))
    return (await repo.users_output([item]))[0]


@router.post("/users", status_code=201)
async def create_user(data: UserCreate, service: Management) -> UserRecord:
    return (await service.repo.users_output([await service.create_user(data)]))[0]


@router.patch("/users/{target}")
async def patch_user(target: UUID, data: UserPatch, service: Management) -> UserRecord:
    return (await service.repo.users_output([await service.patch_user(target, data)]))[0]


@router.get("/departments")
async def departments(
    repo: Repo, page: PageNumber = 1, size: PageSize = 20, q: Search = ""
) -> Page[DepartmentRecord]:
    items, total = await repo.read_page(
        repo.departments()
        .where(Department.name.icontains(q, autoescape=True))
        .order_by(Department.code),
        page,
        size,
    )
    return Page(items=[DepartmentRecord.model_validate(item) for item in items], total=total)


@router.get("/departments/tree")
async def department_tree(repo: Repo) -> list[DepartmentRecord]:
    # The visible parent links can be reconstructed without leaking hidden parent identifiers.
    records = list(await repo.db.scalars(repo.departments().order_by(Department.code)))
    scope = {item.id for item in records}
    return [
        DepartmentRecord.model_validate(item).model_copy(
            update={"parent_id": item.parent_id if item.parent_id in scope else None}
        )
        for item in records
    ]


@router.get("/departments/{target}")
async def get_department(target: UUID, repo: Repo) -> DepartmentRecord:
    item = require(await repo.db.scalar(repo.departments().where(Department.id == target)))
    return DepartmentRecord.model_validate(item)


@router.get("/departments/{target}/members")
async def department_members(
    target: UUID, repo: Repo, page: PageNumber = 1, size: PageSize = 20
) -> Page[UserRecord]:
    await get_department(target, repo)
    items, total = await repo.read_page(
        repo.users()
        .where(UserAccount.primary_department_id == target)
        .order_by(UserAccount.display_name, UserAccount.id),
        page,
        size,
    )
    return Page(items=await repo.users_output(items), total=total)


@router.post("/departments", status_code=201)
async def create_department(data: DepartmentCreate, service: Management) -> DepartmentRecord:
    return DepartmentRecord.model_validate(await service.department_change(data))


@router.patch("/departments/{target}")
async def update_department(
    target: UUID, data: DepartmentPatch, service: Management
) -> DepartmentRecord:
    return DepartmentRecord.model_validate(await service.department_change(data, target))


@router.put("/departments/{target}/supervisors/{user}", status_code=204)
async def grant_scope(target: UUID, user: UUID, data: GrantInput, service: Management) -> Response:
    await service.grant(target, user, data.state)
    return Response(status_code=204)


@router.get("/projects")
async def projects(
    repo: Repo, page: PageNumber = 1, size: PageSize = 20, q: Search = ""
) -> Page[ProjectRecord]:
    items, total = await repo.read_page(
        repo.projects().where(Project.name.icontains(q, autoescape=True)).order_by(Project.code),
        page,
        size,
    )
    return Page(items=[ProjectRecord.model_validate(item) for item in items], total=total)


@router.get("/projects/{target}")
async def get_project(target: UUID, repo: Repo) -> ProjectRecord:
    item = require(await repo.db.scalar(repo.projects().where(Project.id == target)))
    return ProjectRecord.model_validate(item)


@router.get("/projects/{target}/members")
async def project_members(target: UUID, repo: Repo) -> list[MemberRecord]:
    await get_project(target, repo)
    return [MemberRecord.model_validate(item) for item in await repo.scoped_members(target)]


@router.post("/projects", status_code=201)
async def create_project(data: ProjectCreate, service: Management) -> ProjectRecord:
    return ProjectRecord.model_validate(await service.project_change(data))


@router.patch("/projects/{target}")
async def patch_project(target: UUID, data: ProjectPatch, service: Management) -> ProjectRecord:
    return ProjectRecord.model_validate(await service.project_change(data, target))


@router.put("/projects/{target}/members/{user}", status_code=204)
async def set_project_member(
    target: UUID, user: UUID, data: ProjectMembership, service: Management
) -> Response:
    await service.project_member(target, user, data)
    return Response(status_code=204)

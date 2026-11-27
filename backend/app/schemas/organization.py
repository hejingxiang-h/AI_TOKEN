from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.models.organization import Role

Label = Annotated[str, Field(min_length=1, max_length=120)]
Code = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")]
State = Literal["active", "disabled"]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class UserCreate(Input):
    login: str = Field(min_length=1, max_length=254)
    display_name: Label
    password: SecretStr = Field(min_length=12, max_length=256)
    primary_department_id: UUID | None = None
    role: Role = Role.USER


class UserPatch(Input):
    display_name: Label | None = None
    primary_department_id: UUID | None = None
    role: Role | None = None
    state: State | None = None


class DepartmentCreate(Input):
    code: Code
    name: Label
    parent_id: UUID | None = None
    owner_id: UUID | None = None


class DepartmentPatch(Input):
    name: Label | None = None
    parent_id: UUID | None = None
    owner_id: UUID | None = None
    state: State | None = None


class ProjectCreate(Input):
    code: Code
    name: Label


class ProjectPatch(Input):
    name: Label | None = None
    state: State | None = None


class ProjectMembership(Input):
    department_id: UUID
    state: State = "active"


class GrantInput(Input):
    state: State = "active"


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state: State


class UserRecord(Record):
    login_normalized: str
    display_name: str
    primary_department_id: UUID | None
    role: Role


class DepartmentRecord(Record):
    code: str
    name: str
    parent_id: UUID | None
    owner_id: UUID | None


class ProjectRecord(Record):
    code: str
    name: str


class MemberRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    department_id: UUID
    state: State


class Page[T](BaseModel):
    items: list[T]
    total: int

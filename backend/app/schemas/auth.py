from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.models.organization import Role


class Credentials(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=256)
    new_password: SecretStr = Field(min_length=12, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    login_normalized: str
    display_name: str
    role: Role = Role.USER

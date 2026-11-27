from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import denied
from app.models.auth import UserAccount
from app.models.organization import Role, UserRole
from app.repositories.auth import AuthRepository
from app.schemas.auth import Credentials, CurrentUser, PasswordChange, TokenResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/api/v1", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)
COOKIE = "gateway_refresh"
COOKIE_PATH = "/api/v1/auth"


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


Database = Annotated[AsyncSession, Depends(get_db)]


def get_auth(request: Request, db: Database) -> AuthService:
    return AuthService(
        AuthRepository(db), request.app.state.settings, getattr(request.state, "request_id", None)
    )


Auth = Annotated[AuthService, Depends(get_auth)]


async def authenticate(
    auth: Auth, credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> tuple[UserAccount, UUID]:
    if credential is None:
        raise denied()
    return await auth.authenticate(credential.credentials)


Identity = Annotated[tuple[UserAccount, UUID], Depends(authenticate)]


def attach_refresh(response: Response, auth: AuthService, token: str) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=auth.settings.app_secure_cookies,
        samesite="strict",
        path=COOKIE_PATH,
        max_age=auth.settings.app_refresh_token_seconds,
    )


def clear_refresh(response: Response, auth: AuthService) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(
        COOKIE,
        path=COOKIE_PATH,
        httponly=True,
        secure=auth.settings.app_secure_cookies,
        samesite="strict",
    )


@router.post("/auth/login")
async def login(data: Credentials, auth: Auth, response: Response) -> TokenResponse:
    tokens, refresh = await auth.login(data.login, data.password.get_secret_value())
    attach_refresh(response, auth, refresh)
    return tokens


@router.post("/auth/refresh")
async def refresh(
    auth: Auth, response: Response, token: Annotated[str | None, Cookie(alias=COOKIE)] = None
) -> TokenResponse:
    tokens, replacement = await auth.refresh(token or "")
    attach_refresh(response, auth, replacement)
    return tokens


@router.post("/auth/logout", status_code=204)
async def logout(identity: Identity, auth: Auth, response: Response) -> None:
    await auth.logout(*identity)
    clear_refresh(response, auth)


@router.get("/me")
async def me(identity: Identity, response: Response, db: Database) -> CurrentUser:
    response.headers["Cache-Control"] = "no-store"
    assignment = await db.get(UserRole, identity[0].id)
    return CurrentUser.model_validate(identity[0]).model_copy(
        update={"role": Role(assignment.role_code) if assignment else Role.USER}
    )


@router.post("/auth/password", status_code=204)
async def change_password(
    data: PasswordChange, identity: Identity, auth: Auth, response: Response
) -> None:
    await auth.change_password(
        identity[0], data.current_password.get_secret_value(), data.new_password.get_secret_value()
    )
    clear_refresh(response, auth)

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.auth import (
    decode_access,
    denied,
    dummy_hash,
    encode_access,
    hash_password,
    signing_key,
    token_digest,
    verify_password,
)
from app.core.config import Settings
from app.models.auth import UserAccount, WebSession
from app.repositories.auth import AuthRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(
        self, repository: AuthRepository, settings: Settings, request_id: str | None
    ) -> None:
        self.repo = repository
        self.settings = settings
        self.request_id = request_id

    def tokens(
        self, user: UserAccount, session: WebSession, refresh: str
    ) -> tuple[TokenResponse, str]:
        return TokenResponse(
            access_token=encode_access(
                self.settings,
                user.id,
                session.id,
                user.auth_epoch,
            ),
            expires_in=self.settings.app_access_token_seconds,
        ), refresh

    @staticmethod
    def eligible(user: UserAccount | None, session: WebSession | None, epoch: int) -> bool:
        return bool(
            user
            and user.state == "active"
            and session
            and session.user_id == user.id
            and epoch == user.auth_epoch == session.auth_epoch
            and session.revoked_at is None
            and session.expires_at > datetime.now(UTC)
        )

    async def login(self, login: str, password: str) -> tuple[TokenResponse, str]:
        signing_key(self.settings)
        record = await self.repo.user_by_login(login.strip().casefold())
        expected = record.password_hash if record else dummy_hash
        correct = await verify_password(expected, password)
        user = await self.repo.user(record.id, lock=True) if record and correct else None
        if user is None or user.state != "active" or user.password_hash != expected:
            self.repo.audit(
                record.id if record else None, "auth.login", None, self.request_id, result="denied"
            )
            await self.repo.db.commit()
            raise denied()
        refresh = secrets.token_urlsafe(48)
        session = WebSession(
            user_id=user.id,
            refresh_token_digest=token_digest(refresh),
            auth_epoch=user.auth_epoch,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self.settings.app_refresh_token_seconds),
        )
        self.repo.db.add(session)
        self.repo.audit(user.id, "auth.login", user.id, self.request_id)
        await self.repo.db.flush()
        result = self.tokens(user, session, refresh)
        await self.repo.db.commit()
        return result

    async def refresh(self, refresh: str) -> tuple[TokenResponse, str]:
        signing_key(self.settings)
        if not refresh or len(refresh) > 150:
            raise denied()
        digest = token_digest(refresh)
        record = await self.repo.session_by_digest(digest)
        if record is None:
            raise denied()
        user = await self.repo.user(record.user_id, lock=True)
        session = await self.repo.session(record.id, lock=True)
        if (
            user is None
            or session is None
            or session.refresh_token_digest != digest
            or not self.eligible(user, session, user.auth_epoch)
        ):
            raise denied()
        next_refresh = secrets.token_urlsafe(48)
        session.refresh_token_digest = token_digest(next_refresh)
        result = self.tokens(user, session, next_refresh)
        await self.repo.db.commit()
        return result

    async def authenticate(self, token: str) -> tuple[UserAccount, UUID]:
        user_id, session_id, epoch = decode_access(self.settings, token)
        user, session = await self.repo.user(user_id), await self.repo.session(session_id)
        if user is None or not self.eligible(user, session, epoch):
            raise denied()
        return user, session_id

    async def logout(self, actor: UserAccount, session_id: UUID) -> None:
        session = await self.repo.session(session_id, lock=True)
        if session is not None:
            session.revoked_at = datetime.now(UTC)
        self.repo.audit(actor.id, "auth.logout", actor.id, self.request_id)
        await self.repo.db.commit()

    async def change_password(self, actor: UserAccount, current: str, new: str) -> None:
        user = await self.repo.user(actor.id, lock=True)
        if (
            user is None
            or user.state != "active"
            or not await verify_password(user.password_hash, current)
        ):
            raise denied()
        user.password_hash = await hash_password(new)
        user.auth_epoch += 1
        await self.repo.revoke_sessions(user.id, datetime.now(UTC))
        self.repo.audit(user.id, "auth.password_changed", user.id, self.request_id)
        await self.repo.db.commit()

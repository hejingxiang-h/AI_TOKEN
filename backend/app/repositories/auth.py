from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import AuditEvent, UserAccount, WebSession


class AuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def user(self, user_id: UUID, *, lock: bool = False) -> UserAccount | None:
        return await self.db.get(UserAccount, user_id, populate_existing=lock, with_for_update=lock)

    async def user_by_login(self, login: str) -> UserAccount | None:
        return await self.db.scalar(
            select(UserAccount).where(UserAccount.login_normalized == login)
        )

    async def session(self, session_id: UUID, *, lock: bool = False) -> WebSession | None:
        return await self.db.get(
            WebSession, session_id, populate_existing=lock, with_for_update=lock
        )

    async def session_by_digest(self, digest: str) -> WebSession | None:
        return await self.db.scalar(
            select(WebSession).where(WebSession.refresh_token_digest == digest)
        )

    async def revoke_sessions(self, user_id: UUID, now: datetime) -> None:
        await self.db.execute(
            update(WebSession)
            .where(WebSession.user_id == user_id, WebSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    def audit(
        self,
        actor: UUID | None,
        action: str,
        target: UUID | None,
        request_id: str | None,
        *,
        result: str = "success",
        target_type: str = "user_account",
    ) -> None:
        self.db.add(
            AuditEvent(
                actor_user_id=actor,
                actor_type="user" if actor else "anonymous",
                action=action,
                target_type=target_type,
                target_id=target,
                request_id=request_id,
                result=result,
            )
        )

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import HTTPException

from app.core.config import Settings
from app.models import organization  # noqa: F401

hasher = PasswordHasher()
# A throwaway hash equalizes the password verification work for unknown accounts.
dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def denied() -> HTTPException:
    return HTTPException(
        401, "Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"}
    )


def signing_key(settings: Settings) -> str:
    value = settings.app_jwt_secret
    if value is None or len(value.get_secret_value().encode()) < 32:
        raise HTTPException(503, "Authentication signing key is not configured")
    return value.get_secret_value()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(hasher.hash, password)


async def verify_password(digest: str, password: str) -> bool:
    try:
        return await asyncio.to_thread(hasher.verify, digest, password)
    except VerificationError:
        return False


def encode_access(settings: Settings, user: UUID, session: UUID, epoch: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user),
            "sid": str(session),
            "epoch": epoch,
            "typ": "access",
            "iss": "ai-token-gateway",
            "aud": "gateway-admin",
            "iat": now,
            "exp": now + timedelta(seconds=settings.app_access_token_seconds),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def decode_access(settings: Settings, token: str) -> tuple[UUID, UUID, int]:
    try:
        claims = jwt.decode(
            token,
            signing_key(settings),
            algorithms=["HS256"],
            issuer="ai-token-gateway",
            audience="gateway-admin",
            options={"require": ["sub", "sid", "epoch", "typ", "iat", "exp", "iss", "aud"]},
        )
        if claims["typ"] != "access" or type(claims["epoch"]) is not int:
            raise denied()
        return UUID(claims["sub"]), UUID(claims["sid"]), claims["epoch"]
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise denied() from exc

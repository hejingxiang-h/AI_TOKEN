"""Create the first administrator with an interactive password prompt."""

import asyncio
from getpass import getpass

from sqlalchemy import func, select, text

from app.core.auth import hash_password
from app.core.config import Settings
from app.db.postgres import create_database_engine, create_session_factory
from app.models.auth import UserAccount
from app.models.organization import Role, UserRole


async def create_admin(login: str, password: str) -> None:
    engine = create_database_engine(Settings())
    try:
        async with create_session_factory(engine).begin() as db:
            await db.execute(text("SELECT pg_advisory_xact_lock(63410021)"))
            admin_count = await db.scalar(
                select(func.count())
                .select_from(UserRole)
                .where(UserRole.role_code == Role.SUPER_ADMIN)
            )
            if admin_count:
                raise SystemExit("An administrator already exists.")
            if await db.scalar(select(UserAccount).where(UserAccount.login_normalized == login)):
                raise SystemExit("Login already in use.")
            user = UserAccount(
                login_normalized=login,
                display_name=login[:120],
                password_hash=await hash_password(password),
            )
            db.add(user)
            await db.flush()
            db.add(UserRole(user_id=user.id, role_code=Role.SUPER_ADMIN))
    finally:
        await engine.dispose()


def main() -> None:
    login = input("Administrator login: ").strip().casefold()
    password = getpass("Password (at least 12 characters): ")
    if not 1 <= len(login) <= 254 or not 12 <= len(password) <= 256:
        raise SystemExit("Invalid login or password length.")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")
    asyncio.run(create_admin(login, password))


if __name__ == "__main__":
    main()

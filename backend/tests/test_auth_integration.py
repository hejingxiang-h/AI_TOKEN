import os

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.core.auth import hash_password, token_digest
from app.core.config import Settings
from app.main import create_app
from app.models.auth import AuditEvent, UserAccount, WebSession

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_GATEWAY_POSTGRES") != "1",
    reason="requires an isolated, migrated PostgreSQL database",
)


async def test_auth_lifecycle() -> None:
    settings = Settings(
        app_jwt_secret=SecretStr("test-only-signing-material-for-integration"),
        app_secure_cookies=False,
    )
    assert settings.app_db_name.endswith("_stage_six")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as db:
            actor = UserAccount(
                login_normalized="integration-login",
                display_name="Integration",
                password_hash=await hash_password("test-only-first-password"),
            )
            db.add(actor)
            await db.commit()
            actor_id = actor.id
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                prefix = "/api/v1"
                data = {"login": "Integration-Login", "password": "test-only-first-password"}
                login = await client.post(prefix + "/auth/login", json=data)
                assert login.status_code == 200
                assert "HttpOnly" in login.headers["set-cookie"]
                refresh = client.cookies["gateway_refresh"]
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                assert (await client.get(prefix + "/me", headers=headers)).json()["id"] == str(
                    actor_id
                )
                async with app.state.session_factory() as db:
                    session = await db.scalar(
                        select(WebSession).where(WebSession.user_id == actor_id)
                    )
                    assert session.refresh_token_digest == token_digest(refresh)
                renewal = await client.post(prefix + "/auth/refresh")
                assert renewal.status_code == 200
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    cookies={"gateway_refresh": refresh},
                ) as replay:
                    assert (await replay.post(prefix + "/auth/refresh")).status_code == 401
                updated = await client.post(
                    prefix + "/auth/password",
                    headers=headers,
                    json={
                        "current_password": data["password"],
                        "new_password": "test-only-second-password",
                    },
                )
                assert updated.status_code == 204
                assert (await client.get(prefix + "/me", headers=headers)).status_code == 401
                assert (await client.post(prefix + "/auth/login", json=data)).status_code == 401
                data["password"] = "test-only-second-password"
                login = await client.post(prefix + "/auth/login", json=data)
                assert login.status_code == 200
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                assert (
                    await client.post(prefix + "/auth/logout", headers=headers)
                ).status_code == 204
                assert (await client.get(prefix + "/me", headers=headers)).status_code == 401
                login = await client.post(prefix + "/auth/login", json=data)
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                async with app.state.session_factory() as db:
                    user = await db.get(UserAccount, actor_id)
                    user.state = "disabled"
                    await db.commit()
                assert (await client.get(prefix + "/me", headers=headers)).status_code == 401
                assert (await client.post(prefix + "/auth/refresh")).status_code == 401
                assert (await client.post(prefix + "/auth/login", json=data)).status_code == 401
        finally:
            async with app.state.session_factory() as db:
                await db.execute(delete(AuditEvent).where(AuditEvent.actor_user_id == actor_id))
                await db.execute(delete(WebSession).where(WebSession.user_id == actor_id))
                await db.execute(delete(UserAccount).where(UserAccount.id == actor_id))
                await db.commit()

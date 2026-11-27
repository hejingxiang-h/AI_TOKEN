import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.auth import hash_password
from app.core.config import Settings
from app.integrations.litellm import LiteLLM
from app.main import create_app
from app.models.access import ApiKey
from app.models.auth import UserAccount
from app.models.organization import Role, UserRole

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_GATEWAY_POSTGRES") != "1", reason="requires isolated PostgreSQL"
)


async def test_organization_and_data_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        app_jwt_secret=SecretStr("test-only-signing-material-for-integration"),
        app_secure_cookies=False,
    )
    assert settings.app_db_name.endswith("_stage_six")
    app = create_app(settings)
    prefix = "/api/v1"
    suffix = uuid4().hex
    password = "test-only-organization-password"
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as db:
            root = UserAccount(
                login_normalized=suffix,
                display_name=suffix,
                password_hash=await hash_password(password),
            )
            db.add(root)
            await db.flush()
            db.add(UserRole(user_id=root.id, role_code=Role.SUPER_ADMIN))
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

            async def login(username: str) -> dict[str, str]:
                response = await client.post(
                    prefix + "/auth/login", json={"login": username, "password": password}
                )
                assert response.status_code == 200
                return {"Authorization": "Bearer " + response.json()["access_token"]}

            admin = await login(suffix)

            async def create(endpoint: str, payload: dict) -> dict:
                response = await client.post(prefix + endpoint, headers=admin, json=payload)
                assert response.status_code == 201, response.text
                return response.json()

            d1 = await create("/departments", {"name": "Engineering", "code": "eng-" + suffix})
            d2 = await create("/departments", {"name": "Finance", "code": "fin-" + suffix})
            users = {}
            for label, department, role in [
                ("manager", d1, "DEPARTMENT_MANAGER"),
                ("staff", d1, "USER"),
                ("outside", d2, "USER"),
            ]:
                users[label] = await create(
                    "/users",
                    {
                        "login": label + suffix,
                        "display_name": label + suffix,
                        "password": password,
                        "primary_department_id": department["id"],
                        "role": role,
                    },
                )
            manager = await login("manager" + suffix)
            employee = await login("staff" + suffix)
            grant = f"{prefix}/departments/{d1['id']}/supervisors/{users['manager']['id']}"
            assert (
                await client.put(grant, headers=admin, json={"state": "active"})
            ).status_code == 204
            for headers, total in [(manager, 2), (employee, 1), (admin, 4)]:
                visible = await client.get(
                    prefix + "/users", params={"q": suffix, "size": 1}, headers=headers
                )
                assert visible.status_code == 200
                assert visible.json()["total"] == total
                assert len(visible.json()["items"]) == 1
                assert "password_hash" not in visible.text
            hidden = f"{prefix}/users/{users['outside']['id']}"
            assert (await client.get(hidden, headers=manager)).status_code == 404
            assert (
                await client.patch(hidden, headers=manager, json={"state": "disabled"})
            ).status_code == 403
            assert (await client.get(prefix + "/roles", headers=employee)).status_code == 403
            project = await create("/projects", {"code": "proj-" + suffix, "name": suffix})
            members = f"{prefix}/projects/{project['id']}/members"
            for item, department in [(users["staff"], d1), (users["outside"], d2)]:
                assert (
                    await client.put(
                        f"{members}/{item['id']}",
                        headers=admin,
                        json={"department_id": department["id"]},
                    )
                ).status_code == 204
            visible = await client.get(members, headers=manager)
            assert [item["user_id"] for item in visible.json()] == [users["staff"]["id"]]
            assert (
                await client.put(grant, headers=admin, json={"state": "disabled"})
            ).status_code == 204
            visible = await client.get(prefix + "/users", params={"q": suffix}, headers=manager)
            assert visible.json()["total"] == 1
            assert (
                await client.get(f"{prefix}/projects/{project['id']}", headers=manager)
            ).status_code == 404
            provider = await create("/providers", {"code": "test-" + suffix})
            model = await create(
                "/model-routes",
                {
                    "provider_id": provider["id"],
                    "alias": suffix,
                    "upstream_model": "test",
                    "protocol": "responses",
                },
            )
            model_url = prefix + "/model-routes/" + model["id"]
            assert (await client.get(model_url, headers=employee)).status_code == 403
            price = {
                "currency": "USD",
                "effective_from": "2026-01-01T00:00:00Z",
                "input_price": "0.012345678912",
                "output_price": "1.2",
                "source_ref": "test",
            }
            assert (
                await client.post(model_url + "/prices", headers=admin, json=price)
            ).status_code == 201
            assert (
                await client.post(model_url + "/prices", headers=admin, json=price)
            ).status_code == 409
            prices = await client.get(model_url + "/prices", headers=admin)
            assert prices.json()["items"][0]["input_price"] == price["input_price"]
            assert (await client.post(model_url + "/probe", headers=admin)).json()[
                "status"
            ] == "unavailable"

            async def healthy(_self: LiteLLM, method: str, path: str, **kwargs: object) -> dict:
                assert method == "GET" and path == "/health"
                assert kwargs["params"] == {"model": suffix}
                return {"healthy_endpoints": [{}]}

            monkeypatch.setattr(LiteLLM, "request", healthy)
            assert (await client.post(model_url + "/probe", headers=admin)).json()[
                "status"
            ] == "healthy"

            future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
            payload = {
                "label": suffix,
                "owner_id": users["staff"]["id"],
                "department_id": d1["id"],
                "project_id": project["id"],
                "model_ids": [model["id"]],
                "expires_at": future,
            }
            assert (
                await client.post(prefix + "/keys/grants", headers=employee, json=payload)
            ).status_code == 403
            key = await create("/keys/grants", payload)
            key_url = prefix + "/keys/" + key["id"]
            assert (await client.get(key_url, headers=manager)).status_code == 404
            assert (await client.post(key_url + "/claim", headers=admin)).status_code == 404
            claimed = await client.post(key_url + "/claim", headers=employee)
            assert claimed.status_code == 201 and claimed.headers["Cache-Control"] == "no-store"
            secret = claimed.json()["key"]
            async with app.state.session_factory() as db:
                stored = await db.get(ApiKey, key["id"])
                assert stored.digest == hashlib.sha256(secret.encode()).hexdigest()
            assert (await client.post(key_url + "/claim", headers=employee)).status_code == 409
            assert secret not in (await client.get(key_url, headers=employee)).text
            for state in ["paused", "active", "revoked"]:
                result = await client.patch(key_url, headers=admin, json={"state": state})
                assert result.status_code == 200 and result.json()["state"] == state
            assert (
                await client.patch(key_url, headers=admin, json={"state": "active"})
            ).status_code == 409

            rule = {
                "scope": "key",
                "target_id": key["id"],
                "daily_amount": "0.012345678912",
                "monthly_amount": "0.25",
                "rpm": 100,
                "warning_percent": "80.25",
                "model_ids": [model["id"]],
            }
            quotas = prefix + "/quotas"
            assert (await client.post(quotas, headers=employee, json=rule)).status_code == 403
            quota = await create("/quotas", rule)
            assert (await client.post(quotas, headers=admin, json=rule)).status_code == 409
            quota_url = quotas + "/" + quota["id"]
            assert (await client.get(quota_url, headers=manager)).status_code == 404
            detail = await client.get(quota_url, headers=employee)
            assert detail.json()["daily_amount"] == rule["daily_amount"]
            updated = await client.put(quota_url, headers=admin, json={**rule, "rpm": 101})
            assert updated.status_code == 200 and updated.json()["rpm"] == 101

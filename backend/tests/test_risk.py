import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.auth import hash_password, token_digest
from app.core.config import Settings
from app.main import create_app
from app.models.access import ApiKey, KeyGrant, QuotaRule
from app.models.auth import UserAccount
from app.models.gateway import GatewayEvent, GatewayRequest
from app.models.model_catalog import ModelRoute, PriceVersion, Provider
from app.models.organization import Department, Role, UserRole
from app.models.project import Project
from app.models.risk import RiskAlert
from app.repositories.risk import client_type, signal, source_ip
from app.services.risk import reconcile_risk


def test_metadata_is_classified_without_storing_raw_agent() -> None:
    assert source_ip("2001:db8::1") == "2001:db8::1"
    assert source_ip("192.0.2.3, 192.0.2.4") is None
    assert client_type("OpenAI-Python/2.0 test marker") == "openai_sdk"
    assert client_type("arbitrary user text") == "unknown"


@pytest.mark.skipif(
    os.getenv("TEST_GATEWAY_STAGE_NINE") != "1", reason="requires isolated PostgreSQL"
)
async def test_risk_scan_and_admin_audit() -> None:
    cfg = Settings(app_jwt_secret=SecretStr(uuid4().hex + uuid4().hex), app_secure_cookies=False)
    assert cfg.app_db_name == "gateway_stage_nine"
    app = create_app(cfg)
    seed = uuid4().hex
    secret = uuid4().hex
    password = await hash_password(secret)
    now = datetime.now(UTC)
    async with app.router.lifespan_context(app):
        factory = app.state.session_factory
        async with factory.begin() as db:
            department = Department(code=seed, name=seed)
            project = Project(code=seed, name=seed)
            provider = Provider(code=seed)
            db.add_all([department, project, provider])
            await db.flush()
            admin = UserAccount(login_normalized=seed, display_name=seed, password_hash=password)
            employee = UserAccount(
                login_normalized=seed + "u",
                display_name=seed,
                password_hash=password,
                primary_department_id=department.id,
            )
            route = ModelRoute(
                provider_id=provider.id,
                alias=seed,
                upstream_model=seed,
                protocol="chat_completions",
            )
            db.add_all([admin, employee, route])
            await db.flush()
            db.add(UserRole(user_id=admin.id, role_code=Role.SUPER_ADMIN))
            grant = KeyGrant(
                owner_id=employee.id,
                department_id=department.id,
                project_id=project.id,
                label=seed,
                state="paused",
                expires_at=now + timedelta(days=1),
            )
            price = PriceVersion(
                model_route_id=route.id,
                currency="USD",
                effective_from=now,
                unit_tokens=1,
                input_price=Decimal(1),
                output_price=Decimal(1),
                source_ref="fixture",
            )
            db.add_all([grant, price])
            await db.flush()
            token = "tg_" + uuid4().hex
            db.add(ApiKey(grant_id=grant.id, digest=token_digest(token), hint="test"))
            db.add(
                QuotaRule(
                    scope="user",
                    user_id=employee.id,
                    rpm=10,
                    daily_amount=Decimal(5),
                    monthly_amount=Decimal(5),
                    warning_percent=Decimal(80),
                )
            )
            await db.flush()
            request_ids = []
            for status, fee, settlement in [
                ("success", 5, "settled"),
                ("upstream_error", None, "review"),
            ]:
                rid = uuid4()
                db.add(
                    GatewayRequest(
                        id=rid,
                        key_id=grant.id,
                        user_id=employee.id,
                        department_id=department.id,
                        project_id=project.id,
                        model_id=route.id,
                        provider_id=provider.id,
                        price_id=price.id,
                        currency="USD",
                        protocol=route.protocol,
                        started_at=now - timedelta(seconds=2),
                        finished_at=now,
                        source_ip="192.0.2.88",
                        client_type="openai_sdk",
                        status=status,
                        settlement=settlement,
                        reserved_cost=Decimal(1),
                        platform_cost=Decimal(fee) if fee else None,
                        supplier_cost=Decimal("5.10") if fee else None,
                    )
                )
                request_ids.append(rid)
            await db.flush()
            db.add(
                GatewayEvent(
                    id=seed, request_id=request_ids[1], kind="needs_review", created_at=now
                )
            )
            uid, gid = employee.id, grant.id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("192.0.2.88", 64000)),
            base_url="http://test",
        ) as client:
            for _ in range(3):
                denied = await client.get(
                    "/v1/models", headers={"Authorization": "Bearer " + token}
                )
                assert denied.status_code == 401
            await signal(factory, "gateway_error", "gateway")
            await signal(factory, "usage_write_error", "gateway")
            scan_time = datetime.now(UTC)
            for _ in range(2):
                async with factory.begin() as db:
                    await reconcile_risk(db, scan_time, 2, Decimal("4"), 1, 3)
            async with factory() as db:
                alerts = list(await db.scalars(select(RiskAlert).where(RiskAlert.user_id == uid)))
                assert len(alerts) == 10
                assert sum(a.kind == "quota_threshold" for a in alerts) == 6
                item = next(a for a in alerts if a.kind == "high_frequency")
                alert_id = item.id

            async def login(name: str) -> dict[str, str]:
                response = await client.post(
                    "/api/v1/auth/login", json={"login": name, "password": secret}
                )
                assert response.status_code == 200
                return {"Authorization": "Bearer " + response.json()["access_token"]}

            member, root = await login(seed + "u"), await login(seed)
            for headers, is_admin in ((member, False), (root, True)):
                item = await client.get(
                    "/api/v1/usage/records/" + str(request_ids[0]), headers=headers
                )
                assert item.status_code == 200
                row = item.json()
                assert row["risk_state"] == "flagged" and row["client_type"] == "openai_sdk"
                assert row["source_ip"] == ("192.0.2.88" if is_admin else None)
            page = await client.get("/api/v1/alerts", params={"size": 100}, headers=root)
            assert {"provider_errors", "gateway_error", "usage_write_error", "invalid_key"} <= {
                r["kind"] for r in page.json()["items"]
            }
            personal = await client.get("/api/v1/alerts", params={"size": 100}, headers=member)
            assert personal.json()["total"] == 10
            endpoint = f"/api/v1/alerts/{alert_id}"
            assert (
                await client.patch(endpoint, json={"status": "resolved"}, headers=member)
            ).status_code == 403
            for state in ("acknowledged", "resolved"):
                result = await client.patch(endpoint, json={"status": state}, headers=root)
                assert result.json()["status"] == state
            assert (
                await client.patch(endpoint, json={"status": "pending"}, headers=root)
            ).status_code == 409
            async with factory.begin() as db:
                await reconcile_risk(db, scan_time, 2, Decimal("4"), 1, 3)
            async with factory() as db:
                assert (await db.get(RiskAlert, alert_id)).status == "resolved"
                assert (await db.get(KeyGrant, gid)).state == "paused"
            created = await client.post(
                "/api/v1/users",
                headers=root,
                json={
                    "login": seed + "new",
                    "display_name": "sensitive-marker",
                    "password": secret,
                },
            )
            assert created.status_code == 201, created.text
            deactivated = await client.patch(
                "/api/v1/users/" + created.json()["id"], headers=root, json={"state": "disabled"}
            )
            assert deactivated.status_code == 200
            events = await client.get("/api/v1/audit-events", headers=root, params={"size": 100})
            assert secret not in events.text and token not in events.text
            assert "sensitive-marker" not in events.text
            assert {"user.created", "user.disabled", "alert.resolved", "management.rejected"} <= {
                e["action"] for e in events.json()["items"]
            }
            assert (await client.get("/api/v1/audit-events", headers=member)).status_code == 403

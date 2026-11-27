import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.auth import hash_password
from app.core.config import Settings
from app.main import create_app
from app.models.access import ApiKey, KeyGrant
from app.models.auth import UserAccount
from app.models.gateway import GatewayRequest
from app.models.model_catalog import ModelRoute, PriceVersion, Provider
from app.models.organization import Department, DepartmentGrant, Role, UserRole
from app.models.project import Project
from app.schemas.usage import UsageQuery
from app.services.usage import window_for

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_GATEWAY_STAGE_EIGHT") != "1", reason="requires isolated PostgreSQL"
)


async def test_reporting_timezone() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as db:
            now = datetime(2026, 11, 26, 16, 2, tzinfo=UTC)
            expected = {
                "today": (date(2026, 11, 27), date(2026, 11, 27), 0),
                "yesterday": (date(2026, 11, 26), date(2026, 11, 26), 24),
                "7d": (date(2026, 11, 21), date(2026, 11, 27), 144),
                "30d": (date(2026, 10, 29), date(2026, 11, 27), 696),
                "month": (date(2026, 11, 1), date(2026, 11, 27), 624),
            }
            for preset, (start, end, hours) in expected.items():
                query = UsageQuery.model_validate({"period": preset})
                window = await window_for(db, query, "Asia/Shanghai", now)
                assert (window.start, window.end) == (start, end)
                assert (window.end_at - window.start_at).total_seconds() // 3600 == hours
            window = await window_for(
                db,
                UsageQuery(period="custom", start=date(2026, 3, 8), end=date(2026, 3, 8)),
                "America/New_York",
                now,
            )
            assert window.end_at - window.start_at == timedelta(hours=23)


async def test_usage_aggregation_and_scope() -> None:
    settings = Settings(
        app_jwt_secret=SecretStr(uuid4().hex + uuid4().hex), app_secure_cookies=False
    )
    assert settings.app_db_name == "gateway_stage_eight"
    app = create_app(settings)
    label = uuid4().hex
    password = uuid4().hex
    digest = await hash_password(password)
    now = datetime(2026, 11, 24, 16, 0, tzinfo=UTC)
    async with app.router.lifespan_context(app):
        async with app.state.session_factory.begin() as db:
            a, b = [Department(code=label + x, name=label + x) for x in ("a", "b")]
            project = Project(code=label, name=label)
            provider = Provider(code=label)
            db.add_all([a, b, project, provider])
            await db.flush()
            route = ModelRoute(
                provider_id=provider.id,
                alias=label,
                upstream_model=label,
                protocol="chat_completions",
            )
            db.add(route)
            people = []
            for index, dept in enumerate((a, a, b, b)):
                person = UserAccount(
                    login_normalized=f"{label}{index}",
                    display_name=f"{label}{index}",
                    password_hash=digest,
                    primary_department_id=dept.id,
                )
                db.add(person)
                people.append(person)
            await db.flush()
            db.add_all(
                [
                    UserRole(user_id=people[0].id, role_code=Role.USER),
                    UserRole(user_id=people[1].id, role_code=Role.DEPARTMENT_MANAGER),
                    DepartmentGrant(department_id=a.id, supervisor_user_id=people[1].id),
                    UserRole(user_id=people[3].id, role_code=Role.SUPER_ADMIN),
                ]
            )
            prices = []
            for currency, effective, price in [
                ("USD", now, "1"),
                ("CNY", now, "1"),
                ("USD", now + timedelta(days=1), "100"),
            ]:
                version = PriceVersion(
                    model_route_id=route.id,
                    currency=currency,
                    effective_from=effective,
                    unit_tokens=1,
                    input_price=Decimal(price),
                    output_price=Decimal(price),
                    source_ref="synthetic",
                )
                db.add(version)
                prices.append(version)
            await db.flush()
            request_ids = []
            for index, position, price_index, raw, status, settlement, fee in [
                (
                    0,
                    timedelta(),
                    0,
                    {"input": 2, "output": 3, "total": 5, "cache_read": 1},
                    "success",
                    "settled",
                    "0.1",
                ),
                (1, timedelta(hours=1), 1, None, "upstream_timeout", "review", None),
                (
                    2,
                    timedelta(hours=2),
                    1,
                    {"input": 6, "output": 4, "total": 10},
                    "success",
                    "settled",
                    "1.25",
                ),
                (0, -timedelta(microseconds=1), 0, None, "dispatching", "reserved", None),
                (0, timedelta(days=1), 2, None, "dispatching", "reserved", None),
            ]:
                account = people[index]
                grant = KeyGrant(
                    owner_id=account.id,
                    department_id=account.primary_department_id,
                    project_id=project.id,
                    label=label,
                    expires_at=now + timedelta(days=5),
                )
                db.add(grant)
                await db.flush()
                db.add(ApiKey(grant_id=grant.id, digest=uuid4().hex, hint="test"))
                await db.flush()
                request_id = uuid4()
                request_ids.append(request_id)
                start = now + position
                price = prices[price_index]
                db.add(
                    GatewayRequest(
                        id=request_id,
                        user_id=account.id,
                        department_id=grant.department_id,
                        project_id=project.id,
                        key_id=grant.id,
                        model_id=route.id,
                        provider_id=provider.id,
                        price_id=price.id,
                        currency=price.currency,
                        protocol=route.protocol,
                        started_at=start,
                        finished_at=start + timedelta(milliseconds=250)
                        if status != "dispatching"
                        else None,
                        status=status,
                        settlement=settlement,
                        normalized_usage=raw,
                        reserved_cost=Decimal("2"),
                        platform_cost=Decimal(fee) if fee else None,
                    )
                )
            project_id, outside, historical_price = project.id, b.id, prices[0].id
        root = "/api/v1"
        query = {
            "period": "custom",
            "start": "2026-11-25",
            "end": "2026-11-25",
            "project_id": str(project_id),
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get(root + "/usage/summary")).status_code == 401
            for login, expected in [(0, 1), (1, 2), (3, 3)]:
                reply = await client.post(
                    root + "/auth/login", json={"login": f"{label}{login}", "password": password}
                )
                headers = {"Authorization": "Bearer " + reply.json()["access_token"]}
                summary = await client.get(
                    root + "/dashboard/overview", params=query, headers=headers
                )
                assert summary.status_code == 200, summary.text
                data = summary.json()["metrics"]
                assert data["calls"] == expected
                assert data["total_tokens"] == (15 if login == 3 else 5)
                assert data["unsettled"] == data["unknown_usage"] == int(login != 0)
                assert Decimal(data["average_response_ms"]) == Decimal("250")
                assert {k: Decimal(v) for k, v in data["costs"].items()} == (
                    {"USD": Decimal(".1"), "CNY": Decimal("1.25")}
                    if login == 3
                    else {"USD": Decimal(".1")}
                )
                listed = await client.get(
                    root + "/usage/records", params={**query, "size": 1}, headers=headers
                )
                assert listed.json()["total"] == expected and len(listed.json()["items"]) == 1
                for route_name in (
                    "trend",
                    "by-department",
                    "by-project",
                    "by-user",
                    "by-model",
                    "by-provider",
                    "by-key",
                ):
                    group = await client.get(
                        root + "/usage/" + route_name, params=query, headers=headers
                    )
                    assert group.status_code == 200, group.text
                    assert (
                        sum(item["metrics"]["calls"] for item in group.json()["items"]) == expected
                    )
                hidden = await client.get(
                    root + f"/usage/records/{request_ids[2]}", headers=headers
                )
                assert hidden.status_code == (200 if login == 3 else 404)
                detail = await client.get(
                    root + f"/usage/records/{request_ids[0]}", headers=headers
                )
                assert detail.json()["price_id"] == str(historical_price)
                assert Decimal(detail.json()["platform_cost"]) == Decimal(".1")
                filtered = await client.get(
                    root + "/usage/summary",
                    params={**query, "department_id": str(outside)},
                    headers=headers,
                )
                metrics = filtered.json()["metrics"]
                assert metrics["calls"] == int(login == 3)
                if login != 3:
                    assert metrics["total_tokens"] is None and metrics["costs"] == {}
            assert (
                await client.get(
                    root + "/usage/summary", params={**query, "end": "2099-01-01"}, headers=headers
                )
            ).status_code == 422

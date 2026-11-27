import asyncio
import hashlib
import hmac
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import time
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import func, select
from starlette.types import Message

from app.api import gateway as gateway_api
from app.core.auth import token_digest
from app.core.config import Settings
from app.db.cache import create_redis_client
from app.integrations.gateway_limits import acquire, release
from app.main import create_app
from app.models.access import ApiKey, KeyGrant, KeyModel, QuotaRule
from app.models.auth import UserAccount
from app.models.gateway import GatewayEvent, GatewayRequest
from app.models.model_catalog import ModelRoute, PriceVersion, Provider
from app.models.organization import Department
from app.models.project import Project, ProjectDepartment, ProjectMember
from app.services.gateway_recovery import recover_journal
from app.services.gateway_usage import UsageCollector, cost, normalize


def test_cumulative_sse_and_cost() -> None:
    parser = UsageCollector("messages")
    payload = (
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":3,"output_tokens":1,'
        b'"cache_read_input_tokens":4,"cache_creation_input_tokens":2}}}\r\n\r\n'
        b'data: {"type":"message_delta","usage":{"output_tokens":5}}\n\n'
        b'data: {"type":"message_stop"}\n\n'
    )
    for i in range(0, len(payload), 3):
        parser.feed(payload[i : i + 3])
    assert parser.complete
    usage = normalize("messages", parser.usage)
    assert usage == dict(input=9, output=5, cache_read=4, cache_write=2, reasoning=0, total=14)
    price = PriceVersion(
        input_price=Decimal("1"),
        output_price=Decimal("3"),
        unit_tokens=1,
        cache_read_price=Decimal("0.1"),
        cache_write_price=Decimal("2"),
    )
    assert cost(price, usage) == Decimal("22.4")
    assert (
        normalize(
            "chat_completions",
            {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
        )
        is None
    )


@pytest.mark.skipif(
    os.getenv("TEST_GATEWAY_STAGE_SEVEN") != "1", reason="requires isolated PostgreSQL and Redis"
)
async def test_gateway_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    alias = uuid4().hex
    secret = SecretStr(uuid4().hex + uuid4().hex)
    service_key = SecretStr(uuid4().hex)
    settings = Settings(
        app_litellm_url="http://proxy.invalid",
        app_gateway_callback_secret=secret,
        app_litellm_service_key=service_key,
        app_gateway_input_bounds={alias: 40},
        app_gateway_output_limit=10,
        app_gateway_responses_enabled=True,
    )
    assert settings.app_db_name == "gateway_stage_seven"
    app = create_app(settings)
    token = "tg_" + uuid4().hex + uuid4().hex
    now = datetime.now(UTC)
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 6,
        "total_tokens": 16,
        "prompt_tokens_details": {"cached_tokens": 2},
        "completion_tokens_details": {"reasoning_tokens": 4},
    }
    calls: list[str] = []

    class InterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield ("data: " + json.dumps({"usage": usage}) + "\n\n").encode()
            await asyncio.sleep(60)

    async def proxy(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer " + service_key.get_secret_value()
        call_id = request.headers["x-litellm-call-id"]
        assert call_id != "forged"
        data = json.loads(request.content)
        assert not {"user", "metadata", "litellm_metadata"}.intersection(data)
        calls.append(str(request.url.path))
        headers = {"x-litellm-call-id": call_id, "x-request-id": "mock-supplier"}
        if data.get("messages") == [{"role": "user", "content": "proxy timeout"}]:
            raise httpx.ReadTimeout("simulated upstream timeout")
        if data.get("messages") == [{"role": "user", "content": "proxy connection failed"}]:
            raise httpx.ConnectError("simulated connect failure")
        if request.url.path == "/v1/responses":
            return httpx.Response(
                200, headers=headers, json={"usage": {"input_tokens": 1, "output_tokens": 1}}
            )
        if request.url.path == "/v1/messages":
            return httpx.Response(
                200, headers=headers, json={"usage": {"input_tokens": 1, "output_tokens": 1}}
            )
        if data.get("messages") == [{"role": "user", "content": "disconnect"}]:
            headers["content-type"] = "text/event-stream"
            return httpx.Response(200, headers=headers, stream=InterruptedStream())
        if data.get("stream"):
            assert data["stream_options"]["include_usage"] is True
            headers["content-type"] = "text/event-stream"
            return httpx.Response(
                200,
                headers=headers,
                content="data: " + json.dumps({"usage": usage}) + "\n\ndata: [DONE]\n\n",
            )
        if data.get("messages") == [{"role": "user", "content": "missing usage"}]:
            return httpx.Response(200, headers=headers, json={"id": "incomplete"})
        return httpx.Response(
            200,
            headers=headers,
            json={
                "usage": usage,
                "choices": [
                    {
                        "message": {
                            "tool_calls": [{"type": "function", "function": {"name": "demo"}}]
                        }
                    }
                ],
            },
        )

    async with app.router.lifespan_context(app):
        async with app.state.session_factory.begin() as db:
            department = Department(code=alias, name=alias)
            project = Project(code=alias, name=alias)
            provider = Provider(code=alias)
            db.add_all([department, project, provider])
            await db.flush()
            user = UserAccount(login_normalized=alias, display_name=alias, password_hash="fixture")
            user.primary_department_id = department.id
            route = ModelRoute(
                provider_id=provider.id,
                alias=alias,
                upstream_model=alias,
                protocol="chat_completions",
            )
            db.add_all(
                [user, route, ProjectDepartment(project_id=project.id, department_id=department.id)]
            )
            await db.flush()
            db.add(
                ProjectMember(project_id=project.id, department_id=department.id, user_id=user.id)
            )
            grant = KeyGrant(
                label=alias,
                owner_id=user.id,
                project_id=project.id,
                department_id=department.id,
                state="active",
                expires_at=now + timedelta(days=1),
            )
            db.add(grant)
            await db.flush()
            db.add_all(
                [
                    ApiKey(grant_id=grant.id, digest=token_digest(token), hint="masked"),
                    KeyModel(grant_id=grant.id, model_id=route.id),
                    PriceVersion(
                        model_route_id=route.id,
                        currency="USD",
                        effective_from=now,
                        input_price=Decimal("1"),
                        output_price=Decimal("2"),
                        unit_tokens=100,
                        cache_read_price=Decimal("0.25"),
                        source_ref="mock",
                    ),
                ]
            )
            grant_id, user_id, department_id, project_id, route_id = (
                grant.id,
                user.id,
                department.id,
                project.id,
                route.id,
            )
        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(proxy)) as proxy_client,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            app.state.gateway_http = proxy_client
            headers = {
                "Authorization": "Bearer " + token,
                "x-litellm-call-id": "forged",
                "user-agent": "OpenAI-Python/2.0 test marker",
                "x-forwarded-for": "192.0.2.11",
            }
            assert (await client.get("/v1/models")).status_code == 401
            assert (await client.get("/v1/models", headers=headers)).json()["data"][0][
                "id"
            ] == alias
            body = {
                "model": alias,
                "messages": [{"role": "user", "content": "fixture"}],
                "max_tokens": 5,
                "metadata": {"user_id": "forged"},
                "tools": [{"type": "function", "function": {"name": "demo"}}],
            }
            path = "/v1/chat/completions"
            assert (
                await client.post(path, json={**body, "model": "blocked"}, headers=headers)
            ).status_code == 403
            reply = await client.post(path, json=body, headers=headers)
            assert reply.status_code == 200, reply.text
            assert reply.json()["choices"][0]["message"]["tool_calls"]
            stream = await client.post(path, json={**body, "stream": True}, headers=headers)
            assert stream.status_code == 200 and "[DONE]" in stream.text
            assert len(calls) == 2
            incomplete = await client.post(
                path,
                json={**body, "messages": [{"role": "user", "content": "missing usage"}]},
                headers=headers,
            )
            assert incomplete.status_code == 200
            request_id = incomplete.headers["x-request-id"]
            callback_path = "/internal/v1/gateway/usage"
            raw = json.dumps(
                {
                    "event_id": alias,
                    "request_id": request_id,
                    "proxy_call_id": request_id,
                    "usage": usage,
                }
            ).encode()
            stamp = str(int(time()))
            signed = (
                stamp + "\nPOST\n" + callback_path + "\n" + hashlib.sha256(raw).hexdigest()
            ).encode()
            cb_headers = {
                "x-hook-timestamp": stamp,
                "x-hook-signature": hmac.new(
                    secret.get_secret_value().encode(), signed, "sha256"
                ).hexdigest(),
            }
            assert (await client.post(callback_path, content=raw)).status_code == 401
            for _ in range(2):
                assert (
                    await client.post(callback_path, content=raw, headers=cb_headers)
                ).status_code == 204
            async with app.state.session_factory.begin() as db:
                rows = list(
                    await db.scalars(
                        select(GatewayRequest).where(GatewayRequest.key_id == grant_id)
                    )
                )
                assert len(rows) == 3
                for row in rows:
                    assert row.settlement == "settled" and row.platform_cost == Decimal("0.205")
                    assert (row.user_id, row.department_id, row.project_id) == (
                        user_id,
                        department_id,
                        project_id,
                    )
                    assert row.normalized_usage["reasoning"] == 4
                    assert row.supplier_request_id == "mock-supplier"
                    assert row.client_type == "openai_sdk" and row.source_ip == "127.0.0.1"
                assert {"json", "sse", "callback"} == {row.usage_source for row in rows}
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(GatewayEvent)
                        .where(GatewayEvent.id == "callback:" + alias)
                    )
                    == 1
                )
                grant = await db.get(KeyGrant, grant_id)
                grant.state = "paused"
            assert (await client.post(path, json=body, headers=headers)).status_code == 401
            async with app.state.session_factory.begin() as db:
                grant = await db.get(KeyGrant, grant_id)
                grant.state = "active"
                route = await db.get(ModelRoute, route_id)
                route.protocol = "responses"
            assert (
                await client.post(
                    "/v1/responses", json={"model": alias, "input": "test"}, headers=headers
                )
            ).status_code == 200
            async with app.state.session_factory.begin() as db:
                route = await db.get(ModelRoute, route_id)
                route.protocol = "messages"
            messages_body = {
                **body,
                "tools": [{"name": "demo", "input_schema": {"type": "object"}}],
            }
            assert (
                await client.post(
                    "/v1/messages",
                    json=messages_body,
                    headers={"x-api-key": token, "anthropic-version": "2023-06-01"},
                )
            ).status_code == 200
            async with app.state.session_factory.begin() as db:
                db.add(
                    QuotaRule(
                        scope="key",
                        key_id=grant_id,
                        daily_amount=Decimal("0.01"),
                        monthly_amount=Decimal("0.01"),
                        rpm=60,
                        warning_percent=Decimal("80"),
                    )
                )
            assert (
                await client.post("/v1/messages", json=messages_body, headers=headers)
            ).status_code == 429
            assert len(calls) == 5
            async with app.state.session_factory.begin() as db:
                quota = await db.scalar(select(QuotaRule).where(QuotaRule.key_id == grant_id))
                quota.daily_amount = quota.monthly_amount = Decimal("100")

            async def simulated_db_failure(*args: object, **kwargs: object) -> None:
                raise RuntimeError("simulated commit failure")

            with monkeypatch.context() as patch:
                patch.setattr(gateway_api, "finalize", simulated_db_failure)
                reply = await client.post("/v1/messages", json=messages_body, headers=headers)
                assert reply.status_code == 200
            cursor = await recover_journal(app.state.session_factory, app.state.cache)
            while cursor:
                cursor = await recover_journal(app.state.session_factory, app.state.cache, cursor)
            async with app.state.session_factory() as db:
                recovered = await db.get(GatewayRequest, UUID(reply.headers["x-request-id"]))
                assert recovered.settlement == "settled"
            for content, status, expected in (
                ("proxy timeout", 504, "review"),
                ("proxy connection failed", 503, "released"),
            ):
                reply = await client.post(
                    "/v1/messages",
                    json={**messages_body, "messages": [{"role": "user", "content": content}]},
                    headers=headers,
                )
                assert reply.status_code == status
                async with app.state.session_factory() as db:
                    failed = await db.get(GatewayRequest, UUID(reply.headers["x-request-id"]))
                    assert failed.settlement == expected and failed.platform_cost is None
            async with app.state.session_factory.begin() as db:
                route = await db.get(ModelRoute, route_id)
                route.protocol = "chat_completions"
            began = asyncio.Event()
            request_body = json.dumps(
                {**body, "stream": True, "messages": [{"role": "user", "content": "disconnect"}]}
            ).encode()
            queued = [{"type": "http.request", "body": request_body, "more_body": False}]
            disconnected_id = None

            async def receive() -> Message:
                if queued:
                    return queued.pop()
                await began.wait()
                return {"type": "http.disconnect"}

            async def send(message: Message) -> None:
                nonlocal disconnected_id
                if message["type"] == "http.response.start":
                    disconnected_id = UUID(dict(message["headers"])[b"x-request-id"].decode())
                elif message.get("body"):
                    began.set()

            await asyncio.wait_for(
                app(
                    {
                        "type": "http",
                        "asgi": {"version": "3.0", "spec_version": "2.3"},
                        "method": "POST",
                        "path": path,
                        "root_path": "",
                        "scheme": "http",
                        "http_version": "1.1",
                        "query_string": b"",
                        "headers": [(b"authorization", ("Bearer " + token).encode())],
                    },
                    receive,
                    send,
                ),
                timeout=5,
            )
            assert disconnected_id is not None
            async with app.state.session_factory() as db:
                row = await db.get(GatewayRequest, disconnected_id)
                assert row.status == "client_disconnected" and row.settlement == "review"
                assert row.raw_usage["prompt_tokens"] == usage["prompt_tokens"]
                assert row.platform_cost is None


@pytest.mark.skipif(os.getenv("TEST_GATEWAY_STAGE_SEVEN") != "1", reason="requires isolated Redis")
async def test_redis_admission_limits() -> None:
    async with create_redis_client(Settings()) as cache:
        seed = uuid4().hex
        for dimension, rpm, tpm, count, tokens, release_first in [
            ("rpm", 1, 100, 10, 1, True),
            ("tpm", 100, 3, 10, 2, True),
            ("parallel", 100, 100, 1, 1, False),
        ]:
            scopes = {seed + dimension + ":department": rpm, seed + dimension + ":key": 20}
            first = uuid4()
            await acquire(cache, first, scopes, tokens, 30, tpm, count)
            if release_first:
                await release(cache, first, scopes)
            with pytest.raises(HTTPException) as denied:
                await acquire(cache, uuid4(), scopes, tokens, 30, tpm, count)
            assert denied.value.status_code == 429
            if not release_first:
                await release(cache, first, scopes)
                await acquire(cache, uuid4(), scopes, tokens, 30, tpm, count)


@pytest.mark.skipif(
    os.getenv("TEST_GATEWAY_REAL_PROXY") != "1", reason="requires LiteLLM and simulated suppliers"
)
async def test_installed_proxy() -> None:
    label = uuid4().hex
    aliases = {
        "poc-openai": "chat_completions",
        "poc-claude": "messages",
        "poc-deepseek": "chat_completions",
    }
    settings = Settings(
        app_gateway_input_bounds={key: 128 for key in aliases}, app_gateway_responses_enabled=True
    )
    assert settings.app_db_name == "gateway_stage_seven"
    app = create_app(settings)
    token = "tg_" + uuid4().hex + uuid4().hex
    now = datetime.now(UTC)
    async with app.router.lifespan_context(app):
        async with app.state.session_factory.begin() as db:
            department = Department(code=label, name=label)
            project = Project(code=label, name=label)
            provider = Provider(code=label)
            db.add_all([department, project, provider])
            await db.flush()
            user = UserAccount(
                login_normalized=label,
                display_name=label,
                password_hash="fixture",
                primary_department_id=department.id,
            )
            db.add_all(
                [user, ProjectDepartment(project_id=project.id, department_id=department.id)]
            )
            await db.flush()
            grant = KeyGrant(
                label=label,
                owner_id=user.id,
                project_id=project.id,
                department_id=department.id,
                state="active",
                expires_at=now + timedelta(hours=1),
            )
            db.add(grant)
            db.add(
                ProjectMember(project_id=project.id, department_id=department.id, user_id=user.id)
            )
            await db.flush()
            grant_id = grant.id
            db.add(ApiKey(grant_id=grant_id, digest=token_digest(token), hint="masked"))
            for alias, protocol in aliases.items():
                route = await db.scalar(select(ModelRoute).where(ModelRoute.alias == alias))
                if route is None:
                    route = ModelRoute(
                        alias=alias,
                        provider_id=provider.id,
                        protocol=protocol,
                        upstream_model=alias,
                    )
                    db.add(route)
                    await db.flush()
                    db.add(
                        PriceVersion(
                            model_route_id=route.id,
                            currency="USD",
                            effective_from=now,
                            input_price=Decimal("1"),
                            output_price=Decimal("2"),
                            unit_tokens=1_000_000,
                            source_ref="simulated",
                        )
                    )
                db.add(KeyModel(grant_id=grant_id, model_id=route.id))
        headers = {"Authorization": "Bearer " + token, "anthropic-version": "2023-06-01"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            base = {"messages": [{"role": "user", "content": "fixture"}], "max_tokens": 32}
            for alias, protocol in aliases.items():
                path = "/v1/messages" if protocol == "messages" else "/v1/chat/completions"
                for stream in (False, True):
                    reply = await client.post(
                        path, json={**base, "model": alias, "stream": stream}, headers=headers
                    )
                    assert reply.status_code == 200, (alias, stream, reply.text[:300])
                    if stream:
                        assert reply.headers["content-type"].startswith("text/event-stream")
            reply = await client.post(
                "/v1/chat/completions",
                json={
                    **base,
                    "model": "poc-openai",
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "parameters": {"type": "object"},
                            },
                        }
                    ],
                },
                headers=headers,
            )
            assert reply.status_code == 200
            assert reply.json()["choices"][0]["message"]["tool_calls"]
            async with app.state.session_factory.begin() as db:
                route = await db.scalar(select(ModelRoute).where(ModelRoute.alias == "poc-openai"))
                route.protocol = "responses"
            try:
                for stream in (False, True):
                    reply = await client.post(
                        "/v1/responses",
                        headers=headers,
                        json={
                            "model": "poc-openai",
                            "input": "fixture",
                            "stream": stream,
                            "max_output_tokens": 32,
                        },
                    )
                    assert reply.status_code == 200, reply.text
                    if stream:
                        assert reply.headers["content-type"].startswith("text/event-stream")
            finally:
                async with app.state.session_factory.begin() as db:
                    route = await db.scalar(
                        select(ModelRoute).where(ModelRoute.alias == "poc-openai")
                    )
                    route.protocol = "chat_completions"
        async with app.state.session_factory() as db:
            rows = list(
                await db.scalars(select(GatewayRequest).where(GatewayRequest.key_id == grant_id))
            )
            assert len(rows) == 9
            assert all(row.settlement == "settled" for row in rows), [
                (row.protocol, row.status, row.usage_source, row.settlement) for row in rows
            ]
            assert all(row.proxy_call_id == row.id.hex for row in rows)

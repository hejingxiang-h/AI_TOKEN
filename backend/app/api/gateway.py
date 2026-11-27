import asyncio
import hmac
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from hashlib import sha256
from time import time
from uuid import UUID, uuid4

import anyio
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.types import Send

from app.api.auth import Database
from app.core.config import Settings
from app.integrations.gateway_limits import release
from app.integrations.gateway_proxy import send
from app.repositories.gateway import GatewayRepository
from app.schemas.gateway import InferenceBody, Protocol, UsageEvent
from app.services.gateway import Admission, admit, finalize
from app.services.gateway_recovery import forget, journal
from app.services.gateway_usage import UsageCollector, clean_usage

router = APIRouter(tags=["model gateway"])
logger = logging.getLogger(__name__)
MAX_BYTES = 2_000_000

FIELDS = {
    "chat_completions": {
        "model",
        "stream",
        "messages",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "top_p",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "stream_options",
        "stop",
        "response_format",
    },
    "responses": {
        "model",
        "stream",
        "input",
        "instructions",
        "max_output_tokens",
        "temperature",
        "top_p",
        "tools",
        "tool_choice",
        "parallel_tool_calls",
        "text",
        "reasoning",
        "store",
    },
    "messages": {
        "model",
        "stream",
        "messages",
        "system",
        "max_tokens",
        "temperature",
        "top_p",
        "top_k",
        "tools",
        "tool_choice",
        "stop_sequences",
    },
}


def caller_key(request: Request, alternate: bool = False) -> str:
    bearer = request.headers.getlist("authorization")
    api_key = request.headers.getlist("x-api-key")
    if len(bearer) + len(api_key) != 1 or (api_key and not alternate):
        raise HTTPException(401, "Exactly one API key is required")
    if api_key:
        return api_key[0]
    scheme, _, token = bearer[0].partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Bearer API key required")
    return token


async def bounded_body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "Request body is too large")
    return bytes(body)


def check_tools(protocol: Protocol, body: dict) -> None:
    tools = body.get("tools", [])
    if not isinstance(tools, list):
        raise HTTPException(400, "Invalid tools")
    for tool in tools:
        if not isinstance(tool, dict):
            raise HTTPException(400, "Invalid tool")
        if protocol == "messages":
            custom = tool.get("type") in (None, "custom") and isinstance(
                tool.get("input_schema"), dict
            )
        else:
            custom = tool.get("type") == "function"
        if not custom:
            raise HTTPException(400, "Only client-executed function tools are supported")


async def payload(request: Request, protocol: Protocol, settings: Settings) -> tuple[dict, int]:
    try:
        incoming = InferenceBody.model_validate_json(await bounded_body(request, MAX_BYTES))
    except ValidationError as exc:
        raise HTTPException(400, "Invalid model request") from exc
    data = incoming.model_dump(include=FIELDS[protocol], exclude_unset=True)
    field = {
        "chat_completions": "max_completion_tokens",
        "responses": "max_output_tokens",
        "messages": "max_tokens",
    }[protocol]
    if protocol == "chat_completions" and "max_tokens" in data:
        if field in data:
            raise HTTPException(400, "Specify a single output limit")
        field = "max_tokens"
    output = data.setdefault(field, settings.app_gateway_output_limit)
    if type(output) is not int or not 1 <= output <= settings.app_gateway_output_limit:
        raise HTTPException(400, "Invalid output limit")
    check_tools(protocol, data)
    if protocol == "chat_completions":
        data.pop("stream_options", None)
        if incoming.stream:
            data["stream_options"] = {"include_usage": True}
    if protocol == "responses":
        data["store"] = False
    return data, output


def enabled(route_protocol: str, settings: Settings) -> bool:
    return route_protocol != "responses" or settings.app_gateway_responses_enabled


@router.get("/v1/models")
async def model_list(request: Request, db: Database) -> dict:
    repo = GatewayRepository(db)
    grant = await repo.authenticate(caller_key(request), datetime.now(UTC))
    models = await repo.models(grant, await repo.quotas(grant))
    return {
        "object": "list",
        "data": [
            {"id": row.alias, "object": "model", "created": 0, "owned_by": "gateway"}
            for row in models
            if enabled(row.protocol, request.app.state.settings)
        ],
    }


def ids(response: httpx.Response) -> tuple[str | None, str | None]:
    proxy = response.headers.get("x-litellm-call-id")
    supplier = response.headers.get("request-id") or response.headers.get("x-request-id")
    return (proxy[:160] if proxy else None, supplier[:160] if supplier else None)


async def finish(
    request: Request,
    request_id: UUID,
    admission: Admission,
    status: str,
    raw: dict,
    source: str,
    upstream: httpx.Response | None,
    *,
    unbilled: bool = False,
    terminal: bool = True,
) -> None:
    with anyio.CancelScope(shield=True):
        try:
            if upstream is not None:
                await upstream.aclose()
        finally:
            try:
                proxy_id, supplier_id = ids(upstream) if upstream is not None else (None, None)
                outcome = dict(
                    status=status,
                    raw=clean_usage(raw),
                    source=source,
                    proxy_id=proxy_id,
                    supplier_id=supplier_id,
                    unbilled=unbilled,
                    terminal=terminal,
                )
                await journal(request.app.state.cache, request_id, outcome)
                for delay in (0, 0.15, 0.4):
                    await asyncio.sleep(delay)
                    try:
                        await finalize(request.app.state.session_factory, request_id, **outcome)
                        await forget(request.app.state.cache, request_id)
                        break
                    except Exception:
                        logger.warning(
                            "gateway settlement retry", extra={"request_id": request_id.hex}
                        )
                else:
                    logger.error(
                        "gateway settlement pending recovery", extra={"request_id": request_id.hex}
                    )
            finally:
                await release(request.app.state.cache, request_id, admission.scopes)


class GatewayStream(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


async def relay(
    request: Request,
    request_id: UUID,
    admission: Admission,
    upstream: httpx.Response,
    protocol: Protocol,
    deadline: float,
) -> AsyncIterator[bytes]:
    parser = UsageCollector(protocol)
    status = "interrupted"
    try:
        async with asyncio.timeout_at(deadline):
            async for chunk in upstream.aiter_bytes():
                parser.feed(chunk)
                yield chunk
        status = "success" if parser.complete else "interrupted"
    except (TimeoutError, httpx.HTTPError):
        # Connection closes without a synthetic terminal event.
        status = "interrupted"
    except (asyncio.CancelledError, GeneratorExit):
        status = "client_disconnected"
        raise
    finally:
        await finish(
            request,
            request_id,
            admission,
            status,
            parser.usage if not parser.oversize else {},
            "sse",
            upstream,
            terminal=parser.complete and not parser.oversize,
        )


async def infer(request: Request, db: Database, protocol: Protocol) -> Response:
    settings: Settings = request.app.state.settings
    if not enabled(protocol, settings):
        raise HTTPException(404, "Protocol is disabled")
    token = caller_key(request, alternate=protocol == "messages")
    body, output = await payload(request, protocol, settings)
    request_id = UUID(request.state.request_id) if hasattr(request.state, "request_id") else uuid4()
    admission = await admit(
        db, settings, request.app.state.cache, token, request_id, protocol, body["model"], output
    )
    deadline = asyncio.get_running_loop().time() + settings.app_gateway_deadline
    upstream = None
    try:
        async with asyncio.timeout_at(deadline):
            upstream = await send(
                request.app.state.gateway_http,
                settings,
                protocol,
                request_id.hex,
                body,
                request.headers,
            )
            if upstream.status_code != 200:
                await finish(
                    request, request_id, admission, "upstream_rejected", {}, "json", upstream
                )
                return JSONResponse(
                    {
                        "error": {
                            "message": "Model proxy rejected the request",
                            "type": "upstream_error",
                        }
                    },
                    status_code=502,
                )
            content_type = upstream.headers.get("content-type", "").split(";")[0].strip()
            if body.get("stream") and content_type == "text/event-stream":
                return GatewayStream(
                    relay(request, request_id, admission, upstream, protocol, deadline),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
                )
            if body.get("stream") or content_type != "application/json":
                raise httpx.ProtocolError("Unexpected model response content type")
            data = bytearray()
            async for chunk in upstream.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES * 4:
                    raise httpx.ProtocolError("Model response exceeds limit")
            response = json.loads(data)
            if not isinstance(response, dict):
                raise ValueError("Unexpected model response")
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        await finish(
            request, request_id, admission, "not_dispatched", {}, "json", upstream, unbilled=True
        )
        raise HTTPException(503, "Model proxy connection unavailable") from None
    except (TimeoutError, httpx.TimeoutException):
        await finish(request, request_id, admission, "upstream_timeout", {}, "json", upstream)
        raise HTTPException(504, "Model proxy timed out") from None
    except (httpx.HTTPError, ValueError, RecursionError):
        await finish(request, request_id, admission, "upstream_error", {}, "json", upstream)
        raise HTTPException(502, "Model proxy response unavailable") from None
    except asyncio.CancelledError:
        await finish(request, request_id, admission, "client_disconnected", {}, "json", upstream)
        raise
    await finish(
        request,
        request_id,
        admission,
        "success",
        clean_usage(response.get("usage")),
        "json",
        upstream,
    )
    return Response(
        content=bytes(data), media_type="application/json", headers={"Cache-Control": "no-store"}
    )


@router.post("/v1/chat/completions")
async def chat(request: Request, db: Database) -> Response:
    return await infer(request, db, "chat_completions")


@router.post("/v1/responses")
async def responses(request: Request, db: Database) -> Response:
    return await infer(request, db, "responses")


@router.post("/v1/messages")
async def messages(request: Request, db: Database) -> Response:
    return await infer(request, db, "messages")


@router.post("/internal/v1/gateway/usage", status_code=204, include_in_schema=False)
async def callback(request: Request) -> Response:
    secret = request.app.state.settings.app_gateway_callback_secret
    if not secret or len(secret.get_secret_value().encode()) < 32:
        raise HTTPException(404, "Callback unavailable")
    stamp = request.headers.get("x-hook-timestamp", "")
    signature = request.headers.get("x-hook-signature", "")
    if (
        not stamp.isascii()
        or not stamp.isdecimal()
        or len(stamp) > 12
        or abs(time() - int(stamp)) > 300
    ):
        raise HTTPException(401, "Invalid callback signature")
    raw = await bounded_body(request, 32_768)
    signed = (
        stamp.encode() + b"\nPOST\n/internal/v1/gateway/usage\n" + sha256(raw).hexdigest().encode()
    )
    expected = hmac.new(secret.get_secret_value().encode(), signed, sha256).hexdigest()
    if not signature.isascii() or not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid callback signature")
    try:
        event = UsageEvent.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(400, "Invalid usage event") from exc
    await finalize(
        request.app.state.session_factory,
        event.request_id,
        "success",
        event.usage,
        "callback",
        event.proxy_call_id,
        event=event,
    )
    return Response(status_code=204)

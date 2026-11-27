"""Send only validated terminal usage from the internal LiteLLM proxy."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from time import time
from typing import Any
from uuid import UUID

import httpx
from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger(__name__)
PATH = "/internal/v1/gateway/usage"
USAGE_FIELDS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "reasoning_tokens",
}
DETAIL_FIELDS = {
    "prompt_tokens_details",
    "input_tokens_details",
    "completion_tokens_details",
    "output_tokens_details",
}


def extract_usage(response: Any) -> dict:
    usage = (
        response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    )
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return {}
    result = {
        key: value for key, value in usage.items() if key in USAGE_FIELDS and type(value) is int
    }
    for key in DETAIL_FIELDS:
        details = usage.get(key)
        if isinstance(details, dict):
            result[key] = {
                name: value
                for name, value in details.items()
                if name in {"cached_tokens", "reasoning_tokens"} and type(value) is int
            }
    return result


class GatewayCallback(CustomLogger):
    async def async_log_success_event(
        self, kwargs: dict[str, Any], response_obj: Any, start_time: datetime, end_time: datetime
    ) -> None:
        secret = os.environ.get("APP_GATEWAY_CALLBACK_SECRET", "")
        target = os.environ.get("APP_GATEWAY_CALLBACK_BASE_URL", "")
        if len(secret.encode()) < 32 or not target:
            return
        call_id = kwargs.get("litellm_call_id")
        try:
            identifier = UUID(call_id)
        except (ValueError, TypeError, AttributeError):
            return
        usage = extract_usage(response_obj)
        if not usage:
            return
        body = json.dumps(
            {
                "event_id": "terminal-" + identifier.hex,
                "request_id": identifier.hex,
                "proxy_call_id": identifier.hex,
                "usage": usage,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(body).hexdigest()
        async with httpx.AsyncClient(timeout=2.5, trust_env=False) as client:
            for delay in (0, 0.25, 1):
                await asyncio.sleep(delay)
                stamp = str(int(time()))
                data = f"{stamp}\nPOST\n{PATH}\n{digest}".encode()
                signature = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
                try:
                    response = await client.post(
                        target.rstrip("/") + PATH,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-Hook-Timestamp": stamp,
                            "X-Hook-Signature": signature,
                        },
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code == 204:
                    return
                if response.status_code < 500 and response.status_code != 429:
                    break
        logger.warning("Gateway usage callback not acknowledged for call %s", identifier.hex)


handler = GatewayCallback()

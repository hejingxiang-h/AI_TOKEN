"""PoC adapter. Send only event shape and usage field names to the fixture."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from litellm.integrations.custom_logger import CustomLogger

TOKENS = frozenset((
    "prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens",
))


class PocLogger(CustomLogger):
    async def emit(self, event_type: str, kwargs: dict[str, Any], response: Any) -> None:
        logging = kwargs.get("standard_logging_object") or {}
        model = logging.get("model_group") or kwargs.get("model")
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        usage_keys = TOKENS & usage.keys() if isinstance(usage, dict) else set()
        event = {
            "type": event_type,
            "request_id": logging.get("id") or kwargs.get("litellm_call_id"),
            "model": model,
            "protocol": logging.get("call_type") or kwargs.get("call_type"),
            "usage_keys": sorted(usage_keys),
        }
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            await client.post(f"{os.environ['POC_UPSTREAM_ROOT']}/_callback", json=event)

    async def async_log_success_event(
        self, kwargs: dict[str, Any], response_obj: Any, start_time: datetime, end_time: datetime
    ) -> None:
        await self.emit("success", kwargs, response_obj)

    async def async_log_failure_event(
        self, kwargs: dict[str, Any], response_obj: Any, start_time: datetime, end_time: datetime
    ) -> None:
        await self.emit("failure", kwargs, response_obj)


handler = PocLogger()

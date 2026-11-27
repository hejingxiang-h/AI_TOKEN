from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import Settings


class LiteLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def request(self, method: str, path: str, **kwargs: Any) -> dict:
        if self.settings.app_litellm_admin_key is None or self.settings.app_litellm_url is None:
            raise HTTPException(503, "LiteLLM administration is not configured")
        async with httpx.AsyncClient(
            base_url=str(self.settings.app_litellm_url),
            timeout=8,
            trust_env=False,
            headers={
                "Authorization": "Bearer " + self.settings.app_litellm_admin_key.get_secret_value()
            },
        ) as client:
            try:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("Unexpected upstream response")
                return body
            except (httpx.HTTPError, ValueError) as exc:
                raise HTTPException(502, "LiteLLM request did not complete") from exc

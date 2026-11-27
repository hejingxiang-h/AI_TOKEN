from collections.abc import Mapping

import httpx

from app.core.config import Settings

PROTOCOL_PATHS = {
    "chat_completions": "/v1/chat/completions",
    "responses": "/v1/responses",
    "messages": "/v1/messages",
}


def proxy_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(90, connect=5), trust_env=False)


async def send(
    client: httpx.AsyncClient,
    settings: Settings,
    protocol: str,
    request_id: str,
    body: dict,
    caller_headers: Mapping[str, str],
) -> httpx.Response:
    assert settings.app_litellm_url is not None and settings.app_litellm_service_key is not None
    headers = {
        "Authorization": "Bearer " + settings.app_litellm_service_key.get_secret_value(),
        "x-litellm-call-id": request_id,
    }
    if protocol == "messages":
        if caller_headers.get("anthropic-version") == "2023-06-01":
            headers["anthropic-version"] = "2023-06-01"
    target = str(settings.app_litellm_url).rstrip("/") + PROTOCOL_PATHS[protocol]
    return await client.send(
        client.build_request("POST", target, json=body, headers=headers),
        stream=True,
        follow_redirects=False,
    )

"""Exercise the LiteLLM PoC against the synthetic upstream."""
from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

BASE = os.getenv("POC_PROXY_ROOT", "http://127.0.0.1:18400")
FIXTURE = os.getenv("POC_UPSTREAM_ROOT", "http://127.0.0.1:18088")
OPENER = build_opener(ProxyHandler({}))
TOOL = {"type": "function", "function": {"name": "lookup",
        "description": "Return a synthetic lookup result.",
        "parameters": {"type": "object", "properties": {}}}}


def request(root: str, path: str, key: str | None = None,
            payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = Request(root + path, data=data, headers=headers)
    try:
        response = OPENER.open(req, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        wire = response.read().decode()
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            try:
                wire = json.loads(wire)
            except ValueError:
                pass
        return response.status, wire


def chat(key: str, model: str = "poc-openai", **extra: Any) -> tuple[int, Any]:
    return request(BASE, "/v1/chat/completions", key, {
        "model": model, "messages": [{"role": "user", "content": "synthetic prompt"}],
        "max_tokens": 32, **extra,
    })


def events(wire: str) -> Iterator[dict[str, Any]]:
    for line in wire.splitlines():
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            value = json.loads(line[5:].strip())
            if isinstance(value, dict):
                yield value


def expect(status: int, allowed: set[int]) -> None:
    assert status in allowed, f"HTTP {status}, expected {sorted(allowed)}"


def make_key(master: str, **constraints: Any) -> str:
    status, body = request(BASE, "/key/generate", master, {
        "models": ["poc-openai"], "duration": "1h", **constraints,
    })
    expect(status, {200})
    assert isinstance(body.get("key"), str)
    return body["key"]


def read_capture() -> list[dict[str, Any]]:
    status, body = request(FIXTURE, "/_capture")
    expect(status, {200})
    return body["events"]


def run_checks(master: str, protocol_only: bool) -> dict[str, str]:
    results: dict[str, str] = {}
    capture_start = len(read_capture())

    def check(name: str, action: Any) -> None:
        try:
            action()
        except (AssertionError, KeyError, TypeError, OSError, ValueError) as exc:
            results[name] = f"FAIL {type(exc).__name__}: {exc}"
        else:
            results[name] = "PASS"

    def chat_json(model: str) -> None:
        status, body = chat(master, model)
        expect(status, {200})
        for key, expected in {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}.items():
            assert body["usage"][key] == expected, f"{key} mismatch"

    def chat_stream(model: str) -> None:
        status, wire = chat(master, model, stream=True, stream_options={"include_usage": True})
        expect(status, {200})
        frames = list(events(wire))
        assert "data: [DONE]" in wire
        assert any((frame.get("usage") or {}).get("total_tokens") == 18 for frame in frames)

    def responses(stream: bool) -> None:
        status, body = request(BASE, "/v1/responses", master, {
            "model": "poc-openai", "input": "synthetic prompt", "stream": stream, "store": False,
        })
        expect(status, {200})
        if stream:
            body = next((event["response"] for event in events(body)
                         if event.get("type") == "response.completed"), {})
        assert body["usage"]["input_tokens"] == 11
        assert body["usage"]["output_tokens"] == 7
        assert body["usage"]["total_tokens"] == 18

    def messages(stream: bool) -> None:
        status, body = request(BASE, "/v1/messages", master, {
            "model": "poc-claude", "messages": [{"role": "user", "content": "synthetic prompt"}],
            "max_tokens": 32, "stream": stream,
        })
        expect(status, {200})
        if stream:
            frames = list(events(body))
            assert any(frame.get("type") == "message_stop" for frame in frames)
            starting = next((frame["message"]["usage"] for frame in frames
                             if frame.get("type") == "message_start"), {})
            ending = next((frame["usage"] for frame in frames
                           if frame.get("type") == "message_delta"), {})
            assert starting["input_tokens"] == 11
            assert starting["cache_read_input_tokens"] == 5
            assert ending["output_tokens"] == 7
        else:
            assert body["usage"]["input_tokens"] == 11
            assert body["usage"]["output_tokens"] == 7
            assert body["usage"]["cache_read_input_tokens"] == 5

    def tool_roundtrip() -> None:
        status, body = chat(master, tools=[TOOL])
        expect(status, {200})
        reply = body["choices"][0]["message"]
        call = reply["tool_calls"][0]
        assert call["function"]["name"] == "lookup"
        status, body = chat(master, tools=[TOOL], messages=[
            {"role": "user", "content": "synthetic prompt"},
            {"role": "assistant", "content": None, "tool_calls": reply["tool_calls"]},
            {"role": "tool", "tool_call_id": call["id"], "content": "synthetic result"},
        ])
        expect(status, {200})
        assert body["choices"][0]["message"]["content"] == "ok"

    def callbacks() -> None:
        status, _ = chat(master, messages=[{"role": "user", "content": "poc-upstream-failure"}])
        expect(status, {500, 502, 503})
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            captured = read_capture()[capture_start:]
            delivered = [event for event in captured if event["kind"] == "callback"]
            kinds = {event["type"] for event in delivered if event.get("request_id")}
            if {"success", "failure"} <= kinds:
                return
            time.sleep(0.5)
        raise AssertionError("missing correlated success or failure callback")

    def lifecycle() -> None:
        key = make_key(master)
        expect(chat(key)[0], {200})
        expect(chat(key, "poc-deepseek")[0], {400, 401, 403})
        expect(request(BASE, "/key/block", master, {"key": key})[0], {200})
        expect(chat(key)[0], {400, 401, 403})
        expect(request(BASE, "/key/unblock", master, {"key": key})[0], {200})
        expect(chat(key)[0], {200})
        expect(request(BASE, "/key/delete", master, {"keys": [key]})[0], {200})
        expect(chat(key)[0], {400, 401, 403})

    def rpm_limit() -> None:
        key = make_key(master, rpm_limit=1)
        expect(chat(key)[0], {200})
        expect(chat(key)[0], {429})

    def budget_limit() -> None:
        key = make_key(master, max_budget=0.000001, budget_duration="30d")
        first, _ = chat(key)
        if first in {400, 402, 403, 429}:
            return
        expect(first, {200})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status, _ = chat(key)
            if status in {400, 402, 403, 429}:
                return
            expect(status, {200})
            time.sleep(1)
        raise AssertionError("budget did not cause rejection")

    check("OpenAI Chat JSON usage", lambda: chat_json("poc-openai"))
    check("DeepSeek Chat JSON usage", lambda: chat_json("poc-deepseek"))
    check("OpenAI Chat SSE usage", lambda: chat_stream("poc-openai"))
    check("DeepSeek Chat SSE usage", lambda: chat_stream("poc-deepseek"))
    check("OpenAI Responses JSON usage", lambda: responses(False))
    check("OpenAI Responses SSE usage", lambda: responses(True))
    check("Anthropic Messages JSON cache usage", lambda: messages(False))
    check("Anthropic Messages SSE cache usage", lambda: messages(True))
    check("OpenAI function tool round trip", tool_roundtrip)
    check("Success and failure callbacks", callbacks)
    database_checks = {
        "Virtual key, allowlist, block, unblock and delete": lifecycle,
        "Key requests per minute": rpm_limit,
        "Key budget": budget_limit,
    }
    for name, action in database_checks.items():
        if protocol_only:
            results[name] = "SKIP protocol-only run"
        else:
            check(name, action)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol-only", action="store_true")
    args = parser.parse_args()
    results = run_checks(os.environ["POC_MASTER_KEY"], args.protocol_only)
    print(json.dumps(results, indent=2))
    raise SystemExit(int(any(value.startswith("FAIL") for value in results.values())))


if __name__ == "__main__":
    main()

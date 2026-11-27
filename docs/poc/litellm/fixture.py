"""Deterministic loopback upstream and callback sink for the LiteLLM PoC."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

CREATED = 1760000000
CAPTURE: list[dict[str, Any]] = []
LOCK = Lock()
USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
RESPONSE_USAGE = {
    "input_tokens": 11,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens": 7,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 18,
}
ANTHROPIC_USAGE = {
    "input_tokens": 11,
    "output_tokens": 7,
    "cache_read_input_tokens": 5,
    "cache_creation_input_tokens": 0,
}
TOOL = {"id": "call_poc", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}


def record(item: dict[str, Any]) -> None:
    with LOCK:
        CAPTURE.append(item)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def json_reply(self, value: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("x-request-id", "req_mock_upstream")
        self.send_header("request-id", "req_mock_upstream")
        self.end_headers()
        self.wfile.write(body)

    def stream_reply(self, frames: list[tuple[str, Any]]) -> None:
        lines = []
        for event, value in frames:
            if event:
                lines.append(f"event: {event}")
            payload = value if isinstance(value, str) else json.dumps(value)
            lines.extend((f"data: {payload}", ""))
        body = ("\n".join(lines) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/_health":
            self.json_reply({"ok": True})
        elif path == "/_capture":
            with LOCK:
                captured = list(CAPTURE)
            self.json_reply({"events": captured})
        else:
            self.json_reply({"error": "unknown path"}, 404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 1_048_576:
                self.json_reply({"error": "invalid size"}, 400)
                return
            data = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            self.json_reply({"error": "invalid JSON"}, 400)
            return
        if not isinstance(data, dict):
            self.json_reply({"error": "object required"}, 400)
            return
        if path == "/_callback":
            allowed = {"type", "request_id", "model", "protocol", "usage_keys"}
            if data.keys() - allowed or data.get("type") not in {"success", "failure"}:
                self.json_reply({"error": "unexpected event"}, 400)
                return
            record({"kind": "callback", **data})
            self.json_reply({"accepted": True})
            return
        record({"kind": "upstream", "path": path, "stream": bool(data.get("stream")),
                "tools": bool(data.get("tools"))})
        if path.endswith("/chat/completions"):
            self.chat(data)
        elif path.endswith("/responses"):
            self.handle_responses(data)
        elif path.endswith("/messages"):
            self.messages(data)
        else:
            self.json_reply({"error": "unknown path"}, 404)

    def chat(self, data: dict[str, Any]) -> None:
        model = data["model"]
        if "poc-upstream-failure" in json.dumps(data.get("messages")):
            self.json_reply({"error": {"message": "synthetic upstream failure",
                                       "type": "server_error"}}, 500)
            return
        base = {"id": "chatcmpl_poc", "created": CREATED, "model": model}
        if data.get("stream"):
            chunk = {**base, "object": "chat.completion.chunk"}
            self.stream_reply([
                ("", {**chunk, "choices": [{"index": 0, "delta": {"role": "assistant",
                      "content": "ok"}, "finish_reason": None}]}),
                ("", {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
                ("", {**chunk, "choices": [], "usage": USAGE}),
                ("", "[DONE]"),
            ])
            return
        is_tool_return = any(message.get("role") == "tool" for message in data.get("messages", []))
        use_tool = data.get("tools") and not is_tool_return
        message = {"role": "assistant", "content": "ok"}
        if use_tool:
            message = {"role": "assistant", "content": None, "tool_calls": [TOOL]}
        self.json_reply({**base, "object": "chat.completion", "usage": USAGE,
                         "choices": [{"index": 0, "message": message,
                                      "finish_reason": "tool_calls" if use_tool else "stop"}]})

    def handle_responses(self, data: dict[str, Any]) -> None:
        item = {"id": "msg_poc", "type": "message", "status": "completed",
                "role": "assistant", "content": [{"type": "output_text", "text": "ok", "annotations": []}]}
        response = {"id": "resp_poc", "object": "response", "created_at": CREATED,
                    "status": "completed", "model": data["model"], "output": [item],
                    "usage": RESPONSE_USAGE, "parallel_tool_calls": False,
                    "tool_choice": "auto", "tools": [], "error": None, "incomplete_details": None}
        if not data.get("stream"):
            self.json_reply(response)
            return
        created = {**response, "status": "in_progress", "output": [], "usage": None}
        self.stream_reply([
            ("response.created", {"type": "response.created", "sequence_number": 0, "response": created}),
            ("response.output_text.delta", {"type": "response.output_text.delta", "sequence_number": 1,
                                           "output_index": 0, "content_index": 0,
                                           "item_id": "msg_poc", "delta": "ok"}),
            ("response.completed", {"type": "response.completed", "sequence_number": 2,
                                    "response": response}),
        ])

    def messages(self, data: dict[str, Any]) -> None:
        message = {"id": "msg_poc", "type": "message", "role": "assistant",
                   "model": data["model"], "content": [{"type": "text", "text": "ok"}],
                   "stop_reason": "end_turn", "stop_sequence": None, "usage": ANTHROPIC_USAGE}
        if not data.get("stream"):
            self.json_reply(message)
            return
        start = {**message, "content": [], "stop_reason": None,
                 "usage": {**ANTHROPIC_USAGE, "output_tokens": 0}}
        frames = [
            ("message_start", {"message": start}),
            ("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "ok"}}),
            ("content_block_stop", {"index": 0}),
            ("message_delta", {"delta": {"stop_reason": "end_turn", "stop_sequence": None},
                               "usage": ANTHROPIC_USAGE}),
            ("message_stop", {}),
        ]
        self.stream_reply([(event, {"type": event, **payload}) for event, payload in frames])


if __name__ == "__main__":
    host = os.environ.get("POC_FIXTURE_BIND", "127.0.0.1")
    port = int(os.environ.get("POC_FIXTURE_PORT", "18088"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()

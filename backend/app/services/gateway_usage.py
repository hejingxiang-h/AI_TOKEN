import json
from decimal import ROUND_UP, Decimal, localcontext

from app.models.model_catalog import PriceVersion

MONEY_QUANTUM = Decimal("0.000000000001")
DIRECT_FIELDS = {
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
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


def clean_usage(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    result = {
        k: v for k, v in raw.items() if k in DIRECT_FIELDS and type(v) is int and 0 <= v <= 2**53
    }
    for field in DETAIL_FIELDS:
        item = raw.get(field)
        if isinstance(item, dict):
            result[field] = {
                k: v
                for k, v in item.items()
                if k in {"cached_tokens", "reasoning_tokens"} and type(v) is int and 0 <= v <= 2**53
            }
    return result


def normalize(protocol: str, usage: dict) -> dict[str, int] | None:
    if protocol == "messages":
        if "input_tokens" not in usage or "output_tokens" not in usage:
            return None
        read = usage.get("cache_read_input_tokens", 0)
        write = usage.get("cache_creation_input_tokens", 0)
        input_tokens = usage["input_tokens"] + read + write
        output = usage["output_tokens"]
        reasoning = usage.get("reasoning_tokens", 0)
    else:
        stem = "prompt" if protocol == "chat_completions" else "input"
        tail = "completion" if protocol == "chat_completions" else "output"
        if stem + "_tokens" not in usage or tail + "_tokens" not in usage:
            return None
        input_tokens, output = usage[stem + "_tokens"], usage[tail + "_tokens"]
        read = usage.get(stem + "_tokens_details", {}).get(
            "cached_tokens", usage.get("prompt_cache_hit_tokens", 0)
        )
        write = 0
        reasoning = usage.get(tail + "_tokens_details", {}).get(
            "reasoning_tokens", usage.get("reasoning_tokens", 0)
        )
    total = input_tokens + output
    if (
        read + write > input_tokens
        or reasoning > output
        or usage.get("total_tokens", total) != total
    ):
        return None
    return dict(
        input=input_tokens,
        output=output,
        cache_read=read,
        cache_write=write,
        reasoning=reasoning,
        total=total,
    )


def cost(price: PriceVersion, usage: dict[str, int]) -> Decimal:
    read, write = usage["cache_read"], usage["cache_write"]
    cache_read = price.cache_read_price if price.cache_read_price is not None else price.input_price
    cache_write = (
        price.cache_write_price if price.cache_write_price is not None else price.input_price
    )
    with localcontext() as ctx:
        ctx.prec = 60
        charge = (
            (usage["input"] - read - write) * price.input_price
            + read * cache_read
            + write * cache_write
            + usage["output"] * price.output_price
        )
        return (charge / price.unit_tokens).quantize(MONEY_QUANTUM, rounding=ROUND_UP)


def upper_cost(price: PriceVersion, input_bound: int, output_bound: int) -> Decimal:
    maximum = max(price.input_price, price.cache_read_price or 0, price.cache_write_price or 0)
    with localcontext() as ctx:
        ctx.prec = 60
        return (
            (input_bound * maximum + output_bound * price.output_price) / price.unit_tokens
        ).quantize(MONEY_QUANTUM, rounding=ROUND_UP)


class UsageCollector:
    def __init__(self, protocol: str) -> None:
        self.protocol = protocol
        self.buffer = bytearray()
        self.lines: list[bytes] = []
        self.frame_size = 0
        self.usage: dict = {}
        self.complete = False
        self.oversize = False

    def feed(self, chunk: bytes) -> None:
        if self.oversize:
            return
        self.buffer.extend(chunk)
        while (offset := self.buffer.find(b"\n")) != -1:
            line = bytes(self.buffer[:offset]).rstrip(b"\r")
            del self.buffer[: offset + 1]
            self.frame_size += len(line)
            if self.frame_size > 2_000_000:
                self.oversize = True
                self.buffer.clear()
                self.lines.clear()
                return
            if not line:
                self.event(b"\n".join(self.lines))
                self.lines.clear()
                self.frame_size = 0
            elif line.startswith(b"data:"):
                self.lines.append(line[5:].lstrip(b" "))
        if len(self.buffer) > 2_000_000:
            self.oversize = True
            self.buffer.clear()
            self.lines.clear()

    def event(self, data: bytes) -> None:
        if data == b"[DONE]" and self.protocol == "chat_completions":
            self.complete = True
            return
        try:
            item = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            return
        if not isinstance(item, dict):
            return
        kind = item.get("type")
        if self.protocol == "messages":
            if kind == "message_start" and isinstance(item.get("message"), dict):
                self.usage.update(clean_usage(item["message"].get("usage")))
            elif kind == "message_delta":
                self.usage.update(clean_usage(item.get("usage")))
            elif kind == "message_stop":
                self.complete = True
        elif self.protocol == "responses" and kind in {"response.completed", "response.incomplete"}:
            response = item.get("response")
            if isinstance(response, dict):
                self.usage = clean_usage(response.get("usage"))
                self.complete = True
        elif self.protocol == "chat_completions":
            self.usage.update(clean_usage(item.get("usage")))

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

Protocol = Literal["chat_completions", "responses", "messages"]


class InferenceBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(min_length=1, max_length=120)
    stream: StrictBool = False


class UsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    request_id: UUID
    proxy_call_id: str = Field(min_length=1, max_length=160)
    usage: dict[str, JsonValue]

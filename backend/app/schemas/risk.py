from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    actor_type: str
    action: str
    target_type: str
    target_id: UUID | None
    request_id: str | None
    result: str
    occurred_at: datetime
    change_summary: dict | None


class AlertRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    status: str
    severity: str
    target_type: str
    target_id: UUID | None
    user_id: UUID | None
    department_id: UUID | None
    evidence: dict
    detected_at: datetime
    last_seen_at: datetime
    updated_at: datetime | None
    updated_by: UUID | None


AlertStatus = Literal["pending", "acknowledged", "resolved"]

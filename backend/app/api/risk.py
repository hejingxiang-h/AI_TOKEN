from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.auth import Database
from app.api.organization import PageNumber, PageSize
from app.api.permissions import Actor, Administrator
from app.models.auth import AuditEvent
from app.models.risk import RiskAlert
from app.repositories.auth import AuthRepository
from app.repositories.risk import RiskRepository
from app.schemas.organization import Page
from app.schemas.risk import AlertRecord, AlertStatus, AuditRecord

router = APIRouter(prefix="/api/v1", tags=["audit and risk"])
Search = Annotated[str, Query(max_length=60)]


class AlertTransition(BaseModel):
    status: AlertStatus


@router.get("/audit-events")
async def events(
    db: Database,
    _actor: Administrator,
    response: Response,
    page: PageNumber = 1,
    size: PageSize = 20,
    q: Search = "",
) -> Page[AuditRecord]:
    response.headers["Cache-Control"] = "private, no-store"
    query = select(AuditEvent).where(AuditEvent.action.icontains(q, autoescape=True))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    items = await db.scalars(
        query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id)
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page(items=[AuditRecord.model_validate(item) for item in items], total=total or 0)


@router.get("/alerts")
async def alerts(
    db: Database,
    actor: Actor,
    response: Response,
    page: PageNumber = 1,
    size: PageSize = 20,
    status: AlertStatus | None = None,
) -> Page[AlertRecord]:
    response.headers["Cache-Control"] = "private, no-store"
    query = RiskRepository(db, actor).alerts()
    if status is not None:
        query = query.where(RiskAlert.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    items = await db.scalars(
        query.order_by(RiskAlert.detected_at.desc(), RiskAlert.id)
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page(items=[AlertRecord.model_validate(item) for item in items], total=total or 0)


@router.patch("/alerts/{target}")
async def transition(
    target: UUID, data: AlertTransition, db: Database, actor: Administrator, request: Request
) -> AlertRecord:
    from datetime import UTC, datetime

    item = await RiskRepository(db, actor).get(target, lock=True)
    if item is None:
        raise HTTPException(404, "Alert not found")
    if item.status != data.status:
        allowed = {
            "pending": {"acknowledged", "resolved"},
            "acknowledged": {"resolved"},
            "resolved": set(),
        }
        if data.status not in allowed[item.status]:
            raise HTTPException(409, "Invalid alert transition")
        old = item.status
        item.status = data.status
        item.updated_at = datetime.now(UTC)
        item.updated_by = actor.user_id
        AuthRepository(db).audit(
            actor.user_id,
            "alert." + data.status,
            item.id,
            getattr(request.state, "request_id", None),
            target_type="risk_alert",
            change_summary={"before": old, "after": data.status},
        )
        await db.commit()
    return AlertRecord.model_validate(item)

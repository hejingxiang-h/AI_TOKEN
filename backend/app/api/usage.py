from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.auth import Database
from app.api.organization import PageNumber, PageSize
from app.api.permissions import Actor
from app.repositories.usage import UsageRepository
from app.schemas.usage import Breakdown, Dimension, RecordPage, Summary, UsageDetail, UsageQuery
from app.services.usage import window_for

router = APIRouter(prefix="/api/v1", tags=["usage"])
Filters = Annotated[UsageQuery, Query()]


@router.get("/dashboard/overview")
@router.get("/usage/summary")
async def summary(
    query: Filters, actor: Actor, db: Database, request: Request, response: Response
) -> Summary:
    response.headers["Cache-Control"] = "private, no-store"
    window = await window_for(db, query, request.app.state.settings.app_enterprise_timezone)
    (group,) = await UsageRepository(db, actor).aggregate(window, query)
    return Summary(window=window, metrics=group.metrics)


@router.get("/usage/trend")
async def trend(
    query: Filters, actor: Actor, db: Database, request: Request, response: Response
) -> Breakdown:
    response.headers["Cache-Control"] = "private, no-store"
    window = await window_for(db, query, request.app.state.settings.app_enterprise_timezone)
    return Breakdown(
        window=window, items=await UsageRepository(db, actor).aggregate(window, query, "day")
    )


@router.get("/usage/by-{dimension}")
async def breakdown(
    dimension: Dimension,
    query: Filters,
    actor: Actor,
    db: Database,
    request: Request,
    response: Response,
) -> Breakdown:
    response.headers["Cache-Control"] = "private, no-store"
    window = await window_for(db, query, request.app.state.settings.app_enterprise_timezone)
    return Breakdown(
        window=window, items=await UsageRepository(db, actor).aggregate(window, query, dimension)
    )


@router.get("/usage/records")
async def records(
    query: Filters,
    actor: Actor,
    db: Database,
    request: Request,
    response: Response,
    page: PageNumber = 1,
    size: PageSize = 20,
) -> RecordPage:
    response.headers["Cache-Control"] = "private, no-store"
    window = await window_for(db, query, request.app.state.settings.app_enterprise_timezone)
    items, total = await UsageRepository(db, actor).records(window, query, page, size)
    return RecordPage(window=window, items=items, total=total)


@router.get("/usage/records/{request_id}")
async def detail(request_id: UUID, actor: Actor, db: Database, response: Response) -> UsageDetail:
    response.headers["Cache-Control"] = "private, no-store"
    item = await UsageRepository(db, actor).detail(request_id)
    if item is None:
        raise HTTPException(404, "Usage record not found")
    return item

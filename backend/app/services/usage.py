from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import DateTime, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.usage import UsageQuery, UsageRange


async def window_for(
    db: AsyncSession, query: UsageQuery, timezone: str, now: datetime | None = None
) -> UsageRange:
    now = now or datetime.now(UTC)
    today = await db.scalar(
        select(
            cast(
                func.timezone(timezone, literal(now, type_=DateTime(timezone=True))),
                DateTime(timezone=False),
            )
        )
    )
    day = today.date()
    if query.period == "custom":
        if query.start is None or query.end is None:
            raise HTTPException(422, "Start and end dates are required")
        start, end = query.start, query.end
    else:
        if query.start is not None or query.end is not None:
            raise HTTPException(422, "Explicit dates require the custom period")
        end = day - timedelta(days=query.period == "yesterday")
        start = {
            "7d": day - timedelta(days=6),
            "30d": day - timedelta(days=29),
            "month": day.replace(day=1),
        }.get(query.period, end)
    if start > end or end > day or (end - start).days >= 90:
        raise HTTPException(422, "Choose up to 90 calendar days ending by today")

    def midnight(value: date):
        return func.timezone(
            timezone, literal(datetime.combine(value, time.min), type_=DateTime(timezone=False))
        )

    start_at, end_at = (
        await db.execute(select(midnight(start), midnight(end + timedelta(days=1))))
    ).one()
    return UsageRange(
        timezone=timezone,
        start=start,
        end=end,
        start_at=start_at.astimezone(UTC),
        end_at=min(end_at, now).astimezone(UTC),
    )

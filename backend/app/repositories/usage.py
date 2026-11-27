from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Date, Numeric, String, cast, distinct, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Principal
from app.models.access import KeyGrant
from app.models.auth import UserAccount
from app.models.gateway import GatewayRequest as Ledger
from app.models.model_catalog import ModelRoute, Provider
from app.models.organization import Department
from app.models.project import Project
from app.schemas.usage import Group, Metrics, UsageDetail, UsageQuery, UsageRange, UsageRecord

DIMENSIONS = {
    "department": (Ledger.department_id, Department.id, Department.name),
    "project": (Ledger.project_id, Project.id, Project.name),
    "user": (Ledger.user_id, UserAccount.id, UserAccount.display_name),
    "model": (Ledger.model_id, ModelRoute.id, ModelRoute.alias),
    "provider": (Ledger.provider_id, Provider.id, Provider.code),
    "key": (Ledger.key_id, KeyGrant.id, KeyGrant.label),
}


class UsageRepository:
    def __init__(self, db: AsyncSession, actor: Principal) -> None:
        self.db = db
        self.scope = actor.within(Ledger.user_id, Ledger.department_id)

    def predicates(self, window: UsageRange, query: UsageQuery) -> list[Any]:
        clauses = [
            self.scope,
            Ledger.started_at >= window.start_at,
            Ledger.started_at < window.end_at,
        ]
        for name, (field, _, _) in DIMENSIONS.items():
            identifier = getattr(query, name + "_id")
            if identifier is not None:
                clauses.append(field == identifier)
        return clauses

    async def aggregate(
        self, window: UsageRange, query: UsageQuery, dimension: str | None = None
    ) -> list[Group]:
        clauses = self.predicates(window, query)
        identifier = label = None
        if dimension == "day":
            identifier = cast(func.timezone(window.timezone, Ledger.started_at), Date)
            label = identifier
        elif dimension is not None:
            identifier, target, label = DIMENSIONS[dimension]
            # This condition references the selected dimension table.
            clauses.append(identifier == target)
        select_keys = (
            [cast(identifier, String).label("id"), cast(label, String).label("label")]
            if identifier is not None
            else []
        )
        tokens = {
            key: Ledger.normalized_usage[key].astext.cast(BigInteger)
            for key in ("input", "output", "cache_read", "cache_write", "total")
        }
        known = tokens["total"].is_not(None)
        completed = Ledger.finished_at.is_not(None)
        success = Ledger.status == "success"
        count = func.count(Ledger.id)
        metrics = select(
            *select_keys,
            func.sum(tokens["input"]).label("input_tokens"),
            func.sum(tokens["output"]).label("output_tokens"),
            func.sum(
                func.coalesce(tokens["cache_read"], 0) + func.coalesce(tokens["cache_write"], 0)
            )
            .filter(known)
            .label("cache_tokens"),
            func.sum(tokens["total"]).label("total_tokens"),
            count.label("calls"),
            count.filter(success).label("successes"),
            count.filter(completed, ~success).label("failures"),
            count.filter(~completed).label("in_progress"),
            func.count(distinct(Ledger.user_id)).label("active_users"),
            func.count(distinct(Ledger.key_id)).label("active_keys"),
            func.round(
                func.avg(
                    cast(
                        func.extract("epoch", Ledger.finished_at - Ledger.started_at) * 1000,
                        Numeric,
                    )
                ).filter(completed),
                3,
            ).label("average_response_ms"),
            count.filter(Ledger.settlement.in_(("reserved", "review"))).label("unsettled"),
            count.filter(~known).label("unknown_usage"),
        ).where(*clauses)
        currency = select(
            *select_keys[:1], Ledger.currency, func.sum(Ledger.platform_cost).label("amount")
        ).where(*clauses, Ledger.settlement == "settled", Ledger.platform_cost.is_not(None))
        if identifier is not None:
            metrics = metrics.group_by(identifier, label)
            currency = currency.group_by(identifier)
        metrics_cte = metrics.cte("usage_metrics")
        currency_cte = currency.group_by(Ledger.currency).cte("usage_currency")
        # Cast to text before PostgreSQL JSON encoding to preserve Decimal precision.
        costs = select(
            *([currency_cte.c.id] if identifier is not None else []),
            func.jsonb_object_agg(
                currency_cte.c.currency, cast(currency_cte.c.amount, String)
            ).label("costs"),
        )
        if identifier is not None:
            costs = costs.group_by(currency_cte.c.id)
        costs_cte = costs.cte("usage_costs")
        joined = metrics_cte.outerjoin(
            costs_cte, metrics_cte.c.id == costs_cte.c.id if identifier is not None else true()
        )
        statement = select(metrics_cte, costs_cte.c.costs).select_from(joined)
        if dimension == "day":
            statement = statement.order_by(metrics_cte.c.id)
        elif dimension is not None:
            statement = statement.order_by(
                metrics_cte.c.total_tokens.desc().nulls_last(), metrics_cte.c.id
            )
        groups = []
        for item in (await self.db.execute(statement)).mappings():
            values = dict(item)
            resolved = values["successes"] + values["failures"]
            rate = (
                (Decimal(values["successes"]) / resolved).quantize(Decimal(".000001"))
                if resolved
                else None
            )
            groups.append(
                Group(
                    id=values.pop("id", "all"),
                    label=values.pop("label", "all"),
                    metrics=Metrics(
                        **{**values, "costs": values["costs"] or {}, "success_rate": rate}
                    ),
                )
            )
        return groups

    def record_query(self):
        return (
            select(Ledger, ModelRoute.alias, Provider.code)
            .join(ModelRoute, ModelRoute.id == Ledger.model_id)
            .join(Provider, Provider.id == Ledger.provider_id)
        )

    @staticmethod
    def record(item: Any, detailed: bool = False) -> UsageRecord:
        row, model, provider = item
        schema = UsageDetail if detailed else UsageRecord
        return schema(
            **{
                name: getattr(row, name)
                for name in schema.model_fields
                if name not in {"model", "provider"}
            },
            model=model,
            provider=provider,
        )

    async def records(
        self, window: UsageRange, query: UsageQuery, page: int, size: int
    ) -> tuple[list[UsageRecord], int]:
        clauses = self.predicates(window, query)
        rows = (
            self.record_query().where(*clauses).order_by(Ledger.started_at.desc(), Ledger.id.desc())
        )
        total = await self.db.scalar(select(func.count()).select_from(Ledger).where(*clauses))
        items = (await self.db.execute(rows.offset((page - 1) * size).limit(size))).all()
        return [self.record(item) for item in items], total or 0

    async def detail(self, request_id: UUID) -> UsageDetail | None:
        item = (
            await self.db.execute(self.record_query().where(self.scope, Ledger.id == request_id))
        ).one_or_none()
        return self.record(item, detailed=True) if item is not None else None

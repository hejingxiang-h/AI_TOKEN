from uuid import UUID

from sqlalchemy import Select, or_, select

from app.models.access import KeyGrant, QuotaRule
from app.models.auth import UserAccount
from app.models.organization import Role
from app.repositories.organization import OrganizationRepository


class AccessRepository(OrganizationRepository):
    def keys(self) -> Select[tuple[KeyGrant]]:
        return select(KeyGrant).where(self.actor.within(KeyGrant.owner_id, KeyGrant.department_id))

    async def key(self, target: UUID, *, lock: bool = False) -> KeyGrant | None:
        query = self.keys().where(KeyGrant.id == target)
        return await self.db.scalar(query.with_for_update() if lock else query)

    def quotas(self) -> Select[tuple[QuotaRule]]:
        query = select(QuotaRule)
        if self.actor.role == Role.SUPER_ADMIN:
            return query
        predicates = [
            QuotaRule.user_id.in_(self.users().with_only_columns(UserAccount.id)),
            QuotaRule.key_id.in_(self.keys().with_only_columns(KeyGrant.id)),
        ]
        if self.actor.role == Role.DEPARTMENT_MANAGER:
            predicates.append(self.actor.department_scope(QuotaRule.department_id))
        return query.where(or_(*predicates))

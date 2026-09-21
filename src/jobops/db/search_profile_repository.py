from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobops.db.models import SearchProfileRecord
from jobops.models.job import WorkMode
from jobops.models.search_profile import (
    HybridLocationHub,
    SalaryFloorPolicy,
    SearchProfile,
    UnknownCompensationPolicy,
)


class SearchProfileRepository(Protocol):
    def save(self, profile: SearchProfile) -> SearchProfile: ...

    def get(self, profile_id: str) -> SearchProfile | None: ...

    def list(
        self,
        *,
        candidate_id: str | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SearchProfile]: ...

    def count(
        self,
        *,
        candidate_id: str | None = None,
        active: bool | None = None,
    ) -> int: ...

    def delete(self, profile_id: str) -> bool: ...


class SqlAlchemySearchProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, profile: SearchProfile) -> SearchProfile:
        record = self.session.get(SearchProfileRecord, profile.profile_id)
        values = self._to_record_values(profile)

        if record is None:
            record = SearchProfileRecord(**values)
            self.session.add(record)
        else:
            for key, value in values.items():
                if key == "created_at":
                    continue
                setattr(record, key, value)

        self.session.flush()
        return self._to_domain(record)

    def get(self, profile_id: str) -> SearchProfile | None:
        record = self.session.get(SearchProfileRecord, profile_id)
        return None if record is None else self._to_domain(record)

    def list(
        self,
        *,
        candidate_id: str | None = None,
        active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SearchProfile]:
        statement = select(SearchProfileRecord)
        statement = self._apply_filters(
            statement,
            candidate_id=candidate_id,
            active=active,
        )
        statement = (
            statement.order_by(
                SearchProfileRecord.created_at.asc(),
                SearchProfileRecord.profile_id,
            )
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(record) for record in self.session.scalars(statement).all()]

    def count(
        self,
        *,
        candidate_id: str | None = None,
        active: bool | None = None,
    ) -> int:
        statement = select(func.count()).select_from(SearchProfileRecord)
        statement = self._apply_filters(
            statement,
            candidate_id=candidate_id,
            active=active,
        )
        return int(self.session.scalar(statement) or 0)

    def delete(self, profile_id: str) -> bool:
        record = self.session.get(SearchProfileRecord, profile_id)
        if record is None:
            return False
        self.session.delete(record)
        self.session.flush()
        return True

    @staticmethod
    def _apply_filters(statement, *, candidate_id: str | None, active: bool | None):
        if candidate_id:
            statement = statement.where(
                SearchProfileRecord.candidate_id == candidate_id.strip()
            )
        if active is not None:
            statement = statement.where(SearchProfileRecord.active.is_(active))
        return statement

    @staticmethod
    def _to_record_values(profile: SearchProfile) -> dict[str, object]:
        now = datetime.now(UTC)
        return {
            "profile_id": profile.profile_id,
            "candidate_id": profile.candidate_id,
            "name": profile.name,
            "role_queries": list(profile.role_queries),
            "required_keywords": list(profile.required_keywords),
            "excluded_keywords": list(profile.excluded_keywords),
            "allowed_work_modes": [mode.value for mode in profile.allowed_work_modes],
            "locations": list(profile.locations),
            "hybrid_location_hubs": [
                hub.model_dump(mode="json") for hub in profile.hybrid_location_hubs
            ],
            "employment_types": list(profile.employment_types),
            "minimum_salary": profile.minimum_salary,
            "salary_currency": profile.salary_currency,
            "salary_floor_policy": profile.salary_floor_policy.value,
            "unknown_compensation_policy": profile.unknown_compensation_policy.value,
            "excluded_companies": list(profile.excluded_companies),
            "allowed_sources": list(profile.allowed_sources),
            "minimum_fit_score": profile.minimum_fit_score,
            "active": profile.active,
            "created_at": profile.created_at or now,
            "updated_at": now,
        }

    @staticmethod
    def _to_domain(record: SearchProfileRecord) -> SearchProfile:
        return SearchProfile(
            profile_id=record.profile_id,
            candidate_id=record.candidate_id,
            name=record.name,
            role_queries=list(record.role_queries or []),
            required_keywords=list(record.required_keywords or []),
            excluded_keywords=list(record.excluded_keywords or []),
            allowed_work_modes=[
                WorkMode(value) for value in (record.allowed_work_modes or [])
            ],
            locations=list(record.locations or []),
            hybrid_location_hubs=[
                HybridLocationHub.model_validate(item)
                for item in (record.hybrid_location_hubs or [])
            ],
            employment_types=list(record.employment_types or []),
            minimum_salary=record.minimum_salary,
            salary_currency=record.salary_currency,
            salary_floor_policy=SalaryFloorPolicy(record.salary_floor_policy),
            unknown_compensation_policy=UnknownCompensationPolicy(
                record.unknown_compensation_policy
            ),
            excluded_companies=list(record.excluded_companies or []),
            allowed_sources=list(record.allowed_sources or []),
            minimum_fit_score=record.minimum_fit_score,
            active=record.active,
            created_at=_as_utc(record.created_at),
            updated_at=_as_utc(record.updated_at),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

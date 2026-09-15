from collections.abc import Iterable

from jobops.models.resume_evidence import (
    EvidenceQuery,
    ResumeEvidenceBase,
    ResumeEvidenceItem,
    ResumeFamilyDefinition,
    VerifiedResumePayload,
)


class ResumeEvidenceStore:
    """Queryable, provenance-aware candidate resume evidence."""

    def __init__(self, evidence_base: ResumeEvidenceBase):
        self.base = evidence_base
        self._items = {item.evidence_id: item for item in evidence_base.items}
        self._families = {family.family_id: family for family in evidence_base.families}

    def get(self, evidence_id: str) -> ResumeEvidenceItem | None:
        return self._items.get(evidence_id)

    def family(self, family_id: str) -> ResumeFamilyDefinition | None:
        return self._families.get(family_id)

    def query(self, query: EvidenceQuery) -> list[ResumeEvidenceItem]:
        items = [item for item in self.base.items if self._matches(item, query)]
        return sorted(items, key=lambda item: item.evidence_id)

    def for_family(
        self,
        family_id: str,
        *,
        verified_only: bool = True,
    ) -> list[ResumeEvidenceItem]:
        family = self._require_family(family_id)
        excluded = set(family.excluded_evidence_ids)
        pinned = set(family.pinned_evidence_ids)
        family_roles = set(family.role_families)
        priority_skills = {skill.casefold() for skill in family.priority_skills}

        selected: dict[str, ResumeEvidenceItem] = {}
        for item in self.base.items:
            if item.evidence_id in excluded:
                continue
            if verified_only and not item.verified:
                continue

            item_roles = set(item.role_families)
            item_skills = {skill.casefold() for skill in item.skills}
            if (
                item.evidence_id in pinned
                or not family_roles
                or bool(item_roles & family_roles)
                or bool(item_skills & priority_skills)
            ):
                selected[item.evidence_id] = item

        return sorted(
            selected.values(),
            key=lambda item: (
                0 if item.evidence_id in pinned else 1,
                item.evidence_id,
            ),
        )

    def verified_payload(
        self,
        evidence_ids: Iterable[str],
        *,
        family_id: str | None = None,
    ) -> VerifiedResumePayload:
        requested = list(dict.fromkeys(evidence_ids))
        if not requested:
            raise ValueError("verified resume payload requires evidence")

        unknown = [item_id for item_id in requested if item_id not in self._items]
        if unknown:
            raise ValueError(f"unknown evidence ids: {unknown}")

        family = self._require_family(family_id) if family_id else None
        if family:
            excluded = set(family.excluded_evidence_ids)
            blocked = [item_id for item_id in requested if item_id in excluded]
            if blocked:
                raise ValueError(f"resume family excludes evidence ids: {blocked}")

        unverified = [item_id for item_id in requested if not self._items[item_id].verified]
        if unverified:
            raise ValueError(f"verified payload cannot use unverified evidence: {unverified}")

        return VerifiedResumePayload(
            candidate_id=self.base.candidate_id,
            family_id=family_id,
            evidence_ids=requested,
        )

    @staticmethod
    def _matches(item: ResumeEvidenceItem, query: EvidenceQuery) -> bool:
        if query.verified_only and not item.verified:
            return False
        if query.kinds and item.kind not in set(query.kinds):
            return False
        if query.role_families and not set(item.role_families) & set(query.role_families):
            return False

        item_skills = {skill.casefold() for skill in item.skills}
        wanted_skills = {skill.casefold() for skill in query.skills}
        if wanted_skills and not item_skills & wanted_skills:
            return False

        item_tags = {tag.casefold() for tag in item.tags}
        wanted_tags = {tag.casefold() for tag in query.tags}
        if wanted_tags and not item_tags & wanted_tags:
            return False
        return True

    def _require_family(self, family_id: str) -> ResumeFamilyDefinition:
        family = self._families.get(family_id)
        if family is None:
            raise ValueError(f"unknown resume family: {family_id}")
        return family

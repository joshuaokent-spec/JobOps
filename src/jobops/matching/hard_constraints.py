import re

from jobops.models.job import JobPosting, WorkMode
from jobops.models.search_profile import (
    SalaryFloorPolicy,
    SearchConstraintResult,
    SearchProfile,
    UnknownCompensationPolicy,
)

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
_ROLE_ALIASES = {
    "ai": ("artificial", "intelligence"),
    "ml": ("machine", "learning"),
}


class HardConstraintMatcher:
    """Evaluate whether a job satisfies a saved Flagship search profile."""

    def evaluate(self, profile: SearchProfile, job: JobPosting) -> SearchConstraintResult:
        reasons: list[str] = []
        codes: list[str] = []

        def reject(code: str, reason: str) -> None:
            codes.append(code)
            reasons.append(reason)

        if not profile.active:
            reject("profile_inactive", "Search profile is inactive.")

        if profile.role_queries and not any(
            self._role_matches(query, job.title) for query in profile.role_queries
        ):
            reject("role", "Job title does not match any requested role.")

        if profile.allowed_work_modes and job.work_mode not in set(profile.allowed_work_modes):
            modes = ", ".join(mode.value for mode in profile.allowed_work_modes)
            reject(
                "work_mode",
                f"Work mode {job.work_mode.value!r} is outside allowed modes: {modes}.",
            )

        if profile.locations and job.work_mode is not WorkMode.REMOTE:
            location = (job.location or "").casefold()
            if not any(value.casefold() in location for value in profile.locations):
                reject("location", "Job location does not match the requested locations.")

        if profile.employment_types:
            employment_type = (job.employment_type or "").casefold()
            if employment_type not in {
                value.casefold() for value in profile.employment_types
            }:
                reject(
                    "employment_type",
                    "Employment type does not match the search profile.",
                )

        if profile.excluded_companies:
            company = job.company.casefold()
            if any(
                excluded.casefold() == company
                for excluded in profile.excluded_companies
            ):
                reject("excluded_company", "Company is excluded by the search profile.")

        if profile.allowed_sources:
            source = (job.source or "").casefold()
            if source not in {value.casefold() for value in profile.allowed_sources}:
                reject("source", "Job source is outside the allowed source set.")

        searchable_text = " ".join(
            [job.title, job.description, " ".join(job.required_skills), " ".join(job.preferred_skills)]
        ).casefold()
        for keyword in profile.required_keywords:
            if keyword.casefold() not in searchable_text:
                reject("required_keyword", f"Required keyword {keyword!r} is missing.")

        for keyword in profile.excluded_keywords:
            if keyword.casefold() in searchable_text:
                reject("excluded_keyword", f"Excluded keyword {keyword!r} is present.")

        salary_reason = self._salary_rejection_reason(profile, job)
        if salary_reason is not None:
            reject("salary_floor", salary_reason)

        return SearchConstraintResult(
            eligible=not reasons,
            violation_codes=codes,
            reasons=reasons,
        )

    @staticmethod
    def _role_matches(query: str, title: str) -> bool:
        query_tokens = _canonical_role_tokens(query)
        title_tokens = _canonical_role_tokens(title)
        if not query_tokens or not title_tokens:
            return False
        return query_tokens.issubset(title_tokens)

    @staticmethod
    def _salary_rejection_reason(
        profile: SearchProfile,
        job: JobPosting,
    ) -> str | None:
        if profile.minimum_salary is None:
            return None

        if job.salary_min is None and job.salary_max is None:
            if (
                profile.unknown_compensation_policy
                is UnknownCompensationPolicy.ALLOW
            ):
                return None
            return "Compensation is unknown and the profile requires a verified salary floor."

        if job.salary_currency is None:
            if (
                profile.unknown_compensation_policy
                is UnknownCompensationPolicy.ALLOW
            ):
                return None
            return "Salary currency is unknown."

        if job.salary_currency.upper() != profile.salary_currency:
            return (
                f"Salary currency {job.salary_currency.upper()} does not match "
                f"{profile.salary_currency}."
            )

        if job.salary_interval not in (None, "year"):
            return "Salary interval is not normalized to annual compensation."

        if profile.salary_floor_policy is SalaryFloorPolicy.MINIMUM_OFFERED:
            if job.salary_min is None:
                if (
                    profile.unknown_compensation_policy
                    is UnknownCompensationPolicy.ALLOW
                ):
                    return None
                return "Salary minimum is unknown; the strict floor cannot be verified."
            if job.salary_min < profile.minimum_salary:
                return (
                    f"Salary minimum {job.salary_min} is below required floor "
                    f"{profile.minimum_salary}."
                )
            return None

        ceiling = job.salary_max if job.salary_max is not None else job.salary_min
        if ceiling is None:
            if (
                profile.unknown_compensation_policy
                is UnknownCompensationPolicy.ALLOW
            ):
                return None
            return "Salary range cannot be verified."
        if ceiling < profile.minimum_salary:
            return (
                f"Salary range tops out at {ceiling}, below required floor "
                f"{profile.minimum_salary}."
            )
        return None


def _canonical_role_tokens(value: str) -> set[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(value.casefold()):
        alias = _ROLE_ALIASES.get(token)
        if alias is None:
            tokens.append(token)
        else:
            tokens.extend(alias)
    return set(tokens)

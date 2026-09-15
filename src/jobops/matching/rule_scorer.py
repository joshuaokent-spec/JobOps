import re

from jobops.models.candidate import CandidateProfile
from jobops.models.job import JobPosting, WorkMode
from jobops.models.scoring import ScoreBreakdown

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.casefold()))


def _normalized_set(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


class BaselineJobScorer:
    """Transparent baseline used before JobOps has enough labels for learned ranking."""

    weights = {
        "title_fit": 0.20,
        "required_skill_fit": 0.30,
        "preferred_skill_fit": 0.10,
        "experience_fit": 0.15,
        "compensation_fit": 0.15,
        "work_mode_fit": 0.10,
    }

    def score(self, candidate: CandidateProfile, job: JobPosting) -> ScoreBreakdown:
        title_fit = self._title_fit(candidate, job)
        required_skill_fit = self._skill_fit(candidate.skills, job.required_skills, empty_value=1.0)
        preferred_skill_fit = self._skill_fit(candidate.skills, job.preferred_skills, empty_value=1.0)
        experience_fit = self._experience_fit(candidate, job)
        compensation_fit = self._compensation_fit(candidate, job)
        work_mode_fit = self._work_mode_fit(candidate, job)

        values = {
            "title_fit": title_fit,
            "required_skill_fit": required_skill_fit,
            "preferred_skill_fit": preferred_skill_fit,
            "experience_fit": experience_fit,
            "compensation_fit": compensation_fit,
            "work_mode_fit": work_mode_fit,
        }
        overall = round(sum(values[name] * weight for name, weight in self.weights.items()) * 100, 1)

        reasons = [
            f"Matched {required_skill_fit:.0%} of required skills.",
            f"Matched {preferred_skill_fit:.0%} of preferred skills.",
            f"Experience fit is {experience_fit:.0%}.",
            f"Compensation fit is {compensation_fit:.0%}.",
            f"Work-mode fit is {work_mode_fit:.0%}.",
        ]

        return ScoreBreakdown(overall=overall, reasons=reasons, **values)

    @staticmethod
    def _title_fit(candidate: CandidateProfile, job: JobPosting) -> float:
        if not candidate.target_roles:
            return 0.5
        job_tokens = _tokens(job.title)
        if not job_tokens:
            return 0.0
        return max(len(job_tokens & _tokens(role)) / len(job_tokens | _tokens(role)) for role in candidate.target_roles)

    @staticmethod
    def _skill_fit(candidate_skills: list[str], job_skills: list[str], *, empty_value: float) -> float:
        desired = _normalized_set(job_skills)
        if not desired:
            return empty_value
        owned = _normalized_set(candidate_skills)
        return len(desired & owned) / len(desired)

    @staticmethod
    def _experience_fit(candidate: CandidateProfile, job: JobPosting) -> float:
        required = job.minimum_years_experience
        if required in (None, 0):
            return 1.0
        return min(candidate.years_experience / required, 1.0)

    @staticmethod
    def _compensation_fit(candidate: CandidateProfile, job: JobPosting) -> float:
        minimum = candidate.minimum_salary
        if minimum is None:
            return 1.0
        if job.salary_max is None and job.salary_min is None:
            return 0.6
        ceiling = job.salary_max if job.salary_max is not None else job.salary_min
        assert ceiling is not None
        if ceiling >= minimum:
            return 1.0
        return max(ceiling / minimum, 0.0)

    @staticmethod
    def _work_mode_fit(candidate: CandidateProfile, job: JobPosting) -> float:
        preferences = _normalized_set(candidate.preferred_work_modes)
        if not preferences:
            return 1.0
        if job.work_mode is WorkMode.UNKNOWN:
            return 0.6
        return 1.0 if job.work_mode.value.casefold() in preferences else 0.0

from jobops.matching import BaselineJobScorer
from jobops.models.candidate import CandidateProfile
from jobops.models.job import JobPosting, WorkMode


def test_strong_job_scores_highly() -> None:
    candidate = CandidateProfile(
        target_roles=["Data Engineer"],
        skills=["Python", "SQL", "PostgreSQL", "FastAPI"],
        years_experience=3,
        preferred_work_modes=["remote"],
        minimum_salary=80000,
    )
    job = JobPosting(
        job_id="1",
        company="Example",
        title="Data Engineer",
        work_mode=WorkMode.REMOTE,
        salary_min=90000,
        salary_max=120000,
        required_skills=["Python", "SQL", "PostgreSQL"],
        preferred_skills=["FastAPI"],
        minimum_years_experience=2,
    )

    score = BaselineJobScorer().score(candidate, job)
    assert score.overall >= 95
    assert score.required_skill_fit == 1
    assert score.work_mode_fit == 1


def test_missing_required_skills_lowers_score() -> None:
    candidate = CandidateProfile(
        target_roles=["Data Engineer"],
        skills=["Python"],
        years_experience=1,
        preferred_work_modes=["remote"],
    )
    job = JobPosting(
        job_id="2",
        company="Example",
        title="Data Engineer",
        work_mode=WorkMode.ONSITE,
        required_skills=["Python", "SQL", "Spark", "Kafka"],
        minimum_years_experience=4,
    )

    score = BaselineJobScorer().score(candidate, job)
    assert score.required_skill_fit == 0.25
    assert score.experience_fit == 0.25
    assert score.work_mode_fit == 0
    assert score.overall < 60

from jobops.matching import HardConstraintMatcher
from jobops.models.job import JobPosting, WorkMode
from jobops.models.search_profile import (
    SalaryFloorPolicy,
    SearchProfile,
    UnknownCompensationPolicy,
)


def _profile(**overrides) -> SearchProfile:
    values = {
        "profile_id": "profile-1",
        "candidate_id": "me",
        "name": "Remote data roles",
        "role_queries": ["Data Engineer"],
        "allowed_work_modes": [WorkMode.REMOTE],
        "minimum_salary": 65000,
        "salary_currency": "USD",
    }
    values.update(overrides)
    return SearchProfile(**values)


def _job(
    job_id: str,
    *,
    title: str = "Senior Data Engineer",
    work_mode: WorkMode = WorkMode.REMOTE,
    salary_min: int | None = 70000,
    salary_max: int | None = 90000,
    currency: str | None = "USD",
    interval: str | None = "year",
) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        company="Example",
        title=title,
        work_mode=work_mode,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
        salary_interval=interval,
        source="lever",
    )


def test_remote_strict_salary_floor_accepts_verified_lower_bound() -> None:
    result = HardConstraintMatcher().evaluate(_profile(), _job("good"))
    assert result.eligible is True
    assert result.violation_codes == []


def test_strict_salary_floor_rejects_range_that_only_reaches_threshold() -> None:
    result = HardConstraintMatcher().evaluate(
        _profile(),
        _job("range", salary_min=60000, salary_max=90000),
    )
    assert result.eligible is False
    assert "salary_floor" in result.violation_codes


def test_range_can_reach_policy_accepts_same_salary_range() -> None:
    profile = _profile(salary_floor_policy=SalaryFloorPolicy.RANGE_CAN_REACH)
    result = HardConstraintMatcher().evaluate(
        profile,
        _job("range", salary_min=60000, salary_max=90000),
    )
    assert result.eligible is True


def test_remote_only_rejects_hybrid_and_unknown_work_mode() -> None:
    matcher = HardConstraintMatcher()
    hybrid = matcher.evaluate(
        _profile(),
        _job("hybrid", work_mode=WorkMode.HYBRID),
    )
    unknown = matcher.evaluate(
        _profile(),
        _job("unknown", work_mode=WorkMode.UNKNOWN),
    )
    assert hybrid.eligible is False
    assert unknown.eligible is False
    assert "work_mode" in hybrid.violation_codes
    assert "work_mode" in unknown.violation_codes


def test_unknown_salary_is_excluded_by_default() -> None:
    result = HardConstraintMatcher().evaluate(
        _profile(),
        _job("unknown-salary", salary_min=None, salary_max=None, currency=None),
    )
    assert result.eligible is False
    assert result.violation_codes == ["salary_floor"]


def test_unknown_salary_can_be_explicitly_allowed() -> None:
    profile = _profile(
        unknown_compensation_policy=UnknownCompensationPolicy.ALLOW,
    )
    result = HardConstraintMatcher().evaluate(
        profile,
        _job("unknown-salary", salary_min=None, salary_max=None, currency=None),
    )
    assert result.eligible is True


def test_requested_role_is_a_hard_constraint() -> None:
    result = HardConstraintMatcher().evaluate(
        _profile(),
        _job("analyst", title="Senior Data Analyst"),
    )
    assert result.eligible is False
    assert "role" in result.violation_codes


def test_role_alias_allows_ai_phrase_matching() -> None:
    profile = _profile(role_queries=["AI Engineer"], minimum_salary=None)
    result = HardConstraintMatcher().evaluate(
        profile,
        _job("ai", title="Senior Artificial Intelligence Engineer"),
    )
    assert result.eligible is True


def test_unannualized_salary_is_rejected_by_default() -> None:
    result = HardConstraintMatcher().evaluate(
        _profile(),
        _job("unknown-interval", interval=None),
    )
    assert result.eligible is False
    assert result.violation_codes == ["salary_floor"]


def test_role_alias_allows_ux_phrase_matching() -> None:
    profile = _profile(role_queries=["UX Analyst"], minimum_salary=None)
    result = HardConstraintMatcher().evaluate(
        profile,
        _job("ux", title="Senior User Experience Analyst"),
    )
    assert result.eligible is True


def test_role_alias_allows_frontend_phrase_matching() -> None:
    profile = _profile(role_queries=["Frontend Developer"], minimum_salary=None)
    result = HardConstraintMatcher().evaluate(
        profile,
        _job("frontend", title="Front End Developer"),
    )
    assert result.eligible is True


def test_remote_job_ignores_hybrid_hub_radius() -> None:
    profile = _profile(
        allowed_work_modes=[WorkMode.REMOTE, WorkMode.HYBRID],
        hybrid_location_hubs=[
            {
                "label": "Lansing, MI",
                "latitude": 42.7325,
                "longitude": -84.5555,
                "radius_miles": 50,
            }
        ],
        minimum_salary=None,
    )
    result = HardConstraintMatcher().evaluate(
        profile,
        JobPosting(
            job_id="remote-anywhere",
            company="Remote Co",
            title="Data Engineer",
            location="San Diego, CA",
            work_mode=WorkMode.REMOTE,
        ),
    )
    assert result.eligible is True


def test_hybrid_job_within_radius_is_eligible() -> None:
    profile = _profile(
        allowed_work_modes=[WorkMode.REMOTE, WorkMode.HYBRID],
        hybrid_location_hubs=[
            {
                "label": "Seattle, WA",
                "latitude": 47.6062,
                "longitude": -122.3321,
                "radius_miles": 50,
            }
        ],
        minimum_salary=None,
    )
    result = HardConstraintMatcher().evaluate(
        profile,
        JobPosting(
            job_id="hybrid-near-seattle",
            company="Hybrid Co",
            title="Data Engineer",
            location="Bellevue, WA",
            work_mode=WorkMode.HYBRID,
            source_metadata={
                "adapter_metadata": {
                    "latitude": 47.6101,
                    "longitude": -122.2015,
                }
            },
        ),
    )
    assert result.eligible is True


def test_hybrid_job_outside_all_radii_is_rejected() -> None:
    profile = _profile(
        allowed_work_modes=[WorkMode.REMOTE, WorkMode.HYBRID],
        hybrid_location_hubs=[
            {
                "label": "Seattle, WA",
                "latitude": 47.6062,
                "longitude": -122.3321,
                "radius_miles": 50,
            },
            {
                "label": "Portland, OR",
                "latitude": 45.5152,
                "longitude": -122.6784,
                "radius_miles": 50,
            },
        ],
        minimum_salary=None,
    )
    result = HardConstraintMatcher().evaluate(
        profile,
        JobPosting(
            job_id="hybrid-far",
            company="Hybrid Co",
            title="Data Engineer",
            location="Boise, ID",
            work_mode=WorkMode.HYBRID,
            source_metadata={
                "adapter_metadata": {
                    "latitude": 43.6150,
                    "longitude": -116.2023,
                }
            },
        ),
    )
    assert result.eligible is False
    assert result.violation_codes == ["hybrid_radius"]

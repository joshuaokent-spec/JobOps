from jobops.ingestion import SourceJobPosting
from jobops.models.job import WorkMode
from jobops.normalization import DeterministicDuplicateDetector, JobNormalizer


def test_source_identity_is_stable_across_content_updates() -> None:
    normalizer = JobNormalizer()
    first = normalizer.normalize(
        SourceJobPosting(
            source="greenhouse",
            source_job_id="123",
            company="Example Corp",
            title="Data Engineer",
            description="Old description",
        )
    )
    second = normalizer.normalize(
        SourceJobPosting(
            source="greenhouse",
            source_job_id="123",
            company="Example Corp",
            title="Data Engineer II",
            description="Updated description",
        )
    )
    assert first.job_id == second.job_id


def test_cross_source_equivalents_share_dedupe_key() -> None:
    normalizer = JobNormalizer()
    greenhouse = normalizer.normalize(
        SourceJobPosting(
            source="greenhouse",
            source_job_id="gh-1",
            company="Example  Corp",
            title=" Data Engineer ",
            location="Remote - US",
            workplace_type="remote",
        )
    )
    lever = normalizer.normalize(
        SourceJobPosting(
            source="lever",
            source_job_id="lv-9",
            company="example corp",
            title="Data Engineer",
            location="Remote",
            workplace_type="remote",
        )
    )

    assert greenhouse.job_id != lever.job_id
    assert greenhouse.dedupe_key == lever.dedupe_key
    assert DeterministicDuplicateDetector().is_duplicate(greenhouse, lever)


def test_location_distinguishes_non_remote_duplicate_key() -> None:
    normalizer = JobNormalizer()
    nyc = normalizer.normalize(
        SourceJobPosting(
            source="lever",
            source_job_id="1",
            company="Example",
            title="Analyst",
            location="New York, NY",
            workplace_type="on-site",
        )
    )
    chicago = normalizer.normalize(
        SourceJobPosting(
            source="greenhouse",
            source_job_id="2",
            company="Example",
            title="Analyst",
            location="Chicago, IL",
            workplace_type="on-site",
        )
    )
    assert nyc.dedupe_key != chicago.dedupe_key


def test_normalizer_strips_html_and_preserves_raw_payload() -> None:
    job = JobNormalizer().normalize(
        SourceJobPosting(
            source="greenhouse",
            source_job_id="3",
            company="Example",
            title="ML Engineer",
            description="<p>Build &amp; ship <strong>models</strong>.</p>",
            raw_payload={"id": 3, "content": "raw"},
        )
    )
    assert job.description == "Build & ship models."
    assert job.source_metadata["raw_payload"] == {"id": 3, "content": "raw"}


def test_hourly_compensation_is_annualized() -> None:
    job = JobNormalizer().normalize(
        SourceJobPosting(
            source="lever",
            source_job_id="4",
            company="Example",
            title="Data Analyst",
            salary_min=40,
            salary_max=50,
            salary_currency="usd",
            salary_interval="hourly",
        )
    )
    assert job.salary_min == 83200
    assert job.salary_max == 104000
    assert job.salary_currency == "USD"
    assert job.salary_interval == "year"


def test_work_mode_prefers_explicit_then_location_signal() -> None:
    explicit = JobNormalizer().normalize(
        SourceJobPosting(
            source="lever",
            source_job_id="5",
            company="Example",
            title="Engineer",
            location="Boston, MA",
            workplace_type="hybrid",
        )
    )
    inferred = JobNormalizer().normalize(
        SourceJobPosting(
            source="greenhouse",
            source_job_id="6",
            company="Example",
            title="Engineer",
            location="Remote - United States",
        )
    )
    assert explicit.work_mode is WorkMode.HYBRID
    assert inferred.work_mode is WorkMode.REMOTE

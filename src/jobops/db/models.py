from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jobops.db.base import Base


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    work_mode: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    salary_interval: Mapped[str | None] = mapped_column(String(32), nullable=True)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_scope: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SearchProfileRecord(Base):
    __tablename__ = "search_profiles"

    profile_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_queries: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_work_modes: Mapped[list[str]] = mapped_column(JSON, default=list)
    locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    employment_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    salary_floor_policy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="minimum_offered",
    )
    unknown_compensation_policy: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="exclude",
    )
    excluded_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    minimum_fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class FlagshipRunRecord(Base):
    __tablename__ = "flagship_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("search_profiles.profile_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_examined: Mapped[int] = mapped_column(Integer, nullable=False)
    total_hard_eligible: Mapped[int] = mapped_column(Integer, nullable=False)
    total_hard_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    total_fit_eligible: Mapped[int] = mapped_column(Integer, nullable=False)
    total_fit_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    prepared_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejection_summary: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


class FlagshipPreparedJobRecord(Base):
    __tablename__ = "flagship_prepared_jobs"

    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("flagship_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    resume_family_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resume_selection_score: Mapped[float] = mapped_column(Float, nullable=False)
    resume_low_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    readiness: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    readiness_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class ApprovalRecord(Base):
    __tablename__ = "approval_items"

    approval_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(40), nullable=False)
    review_band: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    proposed_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verification_findings: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubmitAuthorizationRecord(Base):
    __tablename__ = "submit_authorizations"

    authorization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prepared_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    browser_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_url_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    submit_selector: Mapped[str] = mapped_column(Text, nullable=False)
    submit_control_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    authorized_by: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revoke_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SubmissionAttemptRecord(Base):
    __tablename__ = "submission_attempts"

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("submit_authorizations.authorization_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    application_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    browser_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_url_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    submit_selector: Mapped[str] = mapped_column(Text, nullable=False)
    submit_control_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    submit_invoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    receipt_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_lock_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )
    successful_submission_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )



class FeedbackEventRecord(Base):
    __tablename__ = "feedback_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    candidate_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    resume_family_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    model_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    experiment_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

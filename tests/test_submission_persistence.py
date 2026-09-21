from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.submission_repository import SqlAlchemySubmissionRepository
from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.job import JobPosting
from jobops.models.submission import (
    PreparedSubmissionState,
    SubmissionAttempt,
    SubmissionAttemptStatus,
    SubmissionAuthorizationStatus,
    SubmissionExecutionOutcome,
    SubmissionExecutionRequest,
    SubmitAuthorization,
    SubmitAuthorizationCreate,
)
from jobops.submissions import SubmissionGate

_NOW = datetime(2026, 9, 21, 17, 0, tzinfo=UTC)
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _state() -> PreparedSubmissionState:
    return PreparedSubmissionState(
        application_id="durable-application",
        job_id="durable-job",
        vendor=BrowserAuditVendor.GENERIC,
        prepared_payload_sha256=_HASH_A,
        audit_run_id="durable-audit",
        audit_created_at=_NOW - timedelta(minutes=1),
        browser_session_id="durable-browser-session",
        document_url_sha256=_HASH_B,
        submit_selector="#submit-application",
        submit_control_sha256=_HASH_C,
    )


def _factory(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'submission.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        SqlAlchemyJobRepository(session).save(
            JobPosting(job_id="durable-job", company="Synthetic Co", title="Data Engineer")
        )
        session.commit()
    return factory


class DurableClaimProbeExecutor:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory
        self.observed_consumed = False
        self.observed_executing = False

    def execute(
        self,
        authorization: SubmitAuthorization,
        state: PreparedSubmissionState,
    ) -> SubmissionExecutionOutcome:
        with self.factory() as verification_session:
            repository = SqlAlchemySubmissionRepository(verification_session)
            persisted_authorization = repository.get_authorization(
                authorization.authorization_id
            )
            assert persisted_authorization is not None
            assert (
                persisted_authorization.status
                is SubmissionAuthorizationStatus.CONSUMED
            )
            self.observed_consumed = True

            assert persisted_authorization.attempt_id is not None
            attempt = repository.get_attempt(persisted_authorization.attempt_id)
            assert attempt is not None
            assert attempt.status is SubmissionAttemptStatus.EXECUTING
            self.observed_executing = True

        return SubmissionExecutionOutcome(
            status=SubmissionAttemptStatus.FAILED,
            submit_invoked=False,
            error_code="synthetic_preclick_failure",
        )


def _attempt_from_authorization(
    authorization: SubmitAuthorization,
    *,
    attempt_id: str,
) -> SubmissionAttempt:
    return SubmissionAttempt(
        attempt_id=attempt_id,
        authorization_id=authorization.authorization_id,
        application_id=authorization.application_id,
        job_id=authorization.job_id,
        vendor=authorization.vendor,
        state_fingerprint=authorization.state_fingerprint,
        browser_session_id=authorization.browser_session_id,
        document_url_sha256=authorization.document_url_sha256,
        submit_selector=authorization.submit_selector,
        submit_control_sha256=authorization.submit_control_sha256,
        audit_run_id=authorization.audit_run_id,
        status=SubmissionAttemptStatus.EXECUTING,
        started_at=_NOW,
    )


def test_execution_claim_is_durable_before_executor_runs(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        gate = SubmissionGate(SqlAlchemySubmissionRepository(session))
        state = _state()
        authorization = gate.authorize(
            SubmitAuthorizationCreate(
                state=state,
                authorized_by="Josh",
                note="Authorize durable synthetic submit.",
            ),
            now=_NOW,
        )
        executor = DurableClaimProbeExecutor(factory)

        attempt = gate.execute(
            SubmissionExecutionRequest(
                authorization_id=authorization.authorization_id,
                state=state,
            ),
            executor,
            now=_NOW + timedelta(seconds=1),
        )

        assert executor.observed_consumed is True
        assert executor.observed_executing is True
        assert attempt.status is SubmissionAttemptStatus.FAILED

    with factory() as verification_session:
        repository = SqlAlchemySubmissionRepository(verification_session)
        persisted = repository.get_attempt(attempt.attempt_id)
        assert persisted is not None
        assert persisted.status is SubmissionAttemptStatus.FAILED
        assert repository.get_blocking_attempt(state.application_id) is None


def test_database_execution_lock_rejects_second_attempt(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    state = _state()

    with factory() as setup_session:
        gate = SubmissionGate(SqlAlchemySubmissionRepository(setup_session))
        first = gate.authorize(
            SubmitAuthorizationCreate(
                state=state,
                authorized_by="Josh",
                note="First synthetic authorization.",
            ),
            now=_NOW,
        )
        second = gate.authorize(
            SubmitAuthorizationCreate(
                state=state,
                authorized_by="Josh",
                note="Second synthetic authorization.",
            ),
            now=_NOW,
        )
        setup_session.commit()

    with factory() as first_session:
        first_repository = SqlAlchemySubmissionRepository(first_session)
        claimed = first_repository.claim_authorization(
            first.authorization_id,
            attempt_id="attempt-1",
            consumed_at=_NOW + timedelta(seconds=1),
        )
        assert claimed is not None
        first_attempt = first_repository.create_attempt(
            _attempt_from_authorization(claimed, attempt_id="attempt-1")
        )
        assert first_attempt is not None
        first_repository.persist_execution_claim()

    with factory() as second_session:
        second_repository = SqlAlchemySubmissionRepository(second_session)
        claimed = second_repository.claim_authorization(
            second.authorization_id,
            attempt_id="attempt-2",
            consumed_at=_NOW + timedelta(seconds=2),
        )
        assert claimed is not None
        second_attempt = second_repository.create_attempt(
            _attempt_from_authorization(claimed, attempt_id="attempt-2")
        )
        assert second_attempt is None

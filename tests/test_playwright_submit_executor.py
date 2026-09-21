from datetime import UTC, datetime, timedelta

import pytest
from playwright.sync_api import Page, sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from jobops.db.base import Base
from jobops.db.repositories import SqlAlchemyJobRepository
from jobops.db.submission_repository import SqlAlchemySubmissionRepository
from jobops.models.browser_audit import BrowserAuditVendor
from jobops.models.job import JobPosting
from jobops.models.submission import (
    PreparedSubmissionState,
    SubmissionAttemptStatus,
    SubmissionAuthorizationStatus,
    SubmissionExecutionRequest,
    SubmitAuthorizationCreate,
)
from jobops.submissions import SubmissionAuthorizationInvalidError, SubmissionGate
from jobops.submissions.playwright_executor import (
    PlaywrightFinalSubmitExecutor,
    document_url_sha256,
    submit_control_sha256,
)

_HASH_A = "a" * 64
_NOW = datetime(2026, 9, 21, 17, 0, tzinfo=UTC)
_SESSION_ID = "synthetic-browser-session"

_HTML = """
<!doctype html>
<html>
<body>
  <form id="application">
    <button id="submit-application" type="submit">Submit application</button>
  </form>
  <p id="status">not submitted</p>
  <script>
    window.__submitCount = 0;
    document.querySelector("#application").addEventListener("submit", event => {
      event.preventDefault();
      window.__submitCount += 1;
      document.querySelector("#status").textContent = "submitted";
    });
  </script>
</body>
</html>
"""


def _repository():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    SqlAlchemyJobRepository(session).save(
        JobPosting(job_id="job-123", company="Synthetic Co", title="Data Engineer")
    )
    session.commit()
    return session, SqlAlchemySubmissionRepository(session)


def _state(page: Page) -> PreparedSubmissionState:
    return PreparedSubmissionState(
        application_id="application-123",
        job_id="job-123",
        vendor=BrowserAuditVendor.GENERIC,
        prepared_payload_sha256=_HASH_A,
        audit_run_id="audit-run-123",
        audit_created_at=_NOW - timedelta(minutes=1),
        browser_session_id=_SESSION_ID,
        document_url_sha256=document_url_sha256(page.url),
        submit_selector="#submit-application",
        submit_control_sha256=submit_control_sha256(page, "#submit-application"),
    )


def _probe(page: Page):
    if page.locator("#status").text_content() != "submitted":
        return None
    return {
        "confirmation": "submitted",
        "candidate_email": "candidate@example.com",
        "session_token": "never-persist-this",
    }


def test_synthetic_final_submit_consumes_one_authorization_exactly_once() -> None:
    session, repository = _repository()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(_HTML)
                state = _state(page)
                gate = SubmissionGate(repository)
                authorization = gate.authorize(
                    SubmitAuthorizationCreate(
                        state=state,
                        authorized_by="Josh",
                        note="Authorize this exact synthetic final-submit state.",
                    ),
                    now=_NOW,
                )
                executor = PlaywrightFinalSubmitExecutor(
                    page,
                    browser_session_id=_SESSION_ID,
                    success_probe=_probe,
                )
                request = SubmissionExecutionRequest(
                    authorization_id=authorization.authorization_id,
                    state=state,
                )

                attempt = gate.execute(
                    request,
                    executor,
                    now=_NOW + timedelta(seconds=1),
                )

                assert attempt.status is SubmissionAttemptStatus.SUCCEEDED
                assert attempt.submit_invoked is True
                assert page.evaluate("window.__submitCount") == 1
                persisted = repository.get_authorization(authorization.authorization_id)
                assert persisted is not None
                assert persisted.status is SubmissionAuthorizationStatus.CONSUMED
                assert persisted.browser_session_id == _SESSION_ID
                assert persisted.document_url_sha256 == state.document_url_sha256

                receipt_text = str(attempt.receipt_metadata)
                assert "candidate@example.com" not in receipt_text
                assert "never-persist-this" not in receipt_text
                assert attempt.receipt_metadata["session_token"] == "[OMITTED]"

                with pytest.raises(SubmissionAuthorizationInvalidError, match="consumed"):
                    gate.execute(
                        request,
                        executor,
                        now=_NOW + timedelta(seconds=2),
                    )
                assert page.evaluate("window.__submitCount") == 1
            finally:
                browser.close()
    finally:
        session.close()


def test_live_submit_control_drift_fails_before_click() -> None:
    session, repository = _repository()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(_HTML)
                state = _state(page)
                gate = SubmissionGate(repository)
                authorization = gate.authorize(
                    SubmitAuthorizationCreate(
                        state=state,
                        authorized_by="Josh",
                        note="Authorize exact synthetic state before drift.",
                    ),
                    now=_NOW,
                )
                page.locator("#submit-application").evaluate(
                    "element => { element.textContent = 'Changed submit'; }"
                )
                executor = PlaywrightFinalSubmitExecutor(
                    page,
                    browser_session_id=_SESSION_ID,
                    success_probe=_probe,
                )

                attempt = gate.execute(
                    SubmissionExecutionRequest(
                        authorization_id=authorization.authorization_id,
                        state=state,
                    ),
                    executor,
                    now=_NOW + timedelta(seconds=1),
                )

                assert attempt.status is SubmissionAttemptStatus.FAILED
                assert attempt.submit_invoked is False
                assert attempt.error_code == "submit_control_drift"
                assert page.evaluate("window.__submitCount") == 0
            finally:
                browser.close()
    finally:
        session.close()

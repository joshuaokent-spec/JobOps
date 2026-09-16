"""Create explicit final-submission authorization and attempt tables.

Revision ID: 20260916_0005
Revises: 20260915_0004
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0005"
down_revision: str | Sequence[str] | None = "20260915_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "submit_authorizations",
        sa.Column("authorization_id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=255), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prepared_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("audit_run_id", sa.String(length=255), nullable=False),
        sa.Column("browser_session_id", sa.String(length=255), nullable=False),
        sa.Column("document_url_sha256", sa.String(length=64), nullable=False),
        sa.Column("submit_selector", sa.Text(), nullable=False),
        sa.Column("submit_control_sha256", sa.String(length=64), nullable=False),
        sa.Column("authorized_by", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=200), nullable=True),
        sa.Column("revoke_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("authorization_id"),
    )
    op.create_index(
        op.f("ix_submit_authorizations_application_id"),
        "submit_authorizations",
        ["application_id"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_job_id"),
        "submit_authorizations",
        ["job_id"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_vendor"),
        "submit_authorizations",
        ["vendor"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_audit_run_id"),
        "submit_authorizations",
        ["audit_run_id"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_browser_session_id"),
        "submit_authorizations",
        ["browser_session_id"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_status"),
        "submit_authorizations",
        ["status"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_attempt_id"),
        "submit_authorizations",
        ["attempt_id"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_created_at"),
        "submit_authorizations",
        ["created_at"],
    )
    op.create_index(
        op.f("ix_submit_authorizations_expires_at"),
        "submit_authorizations",
        ["expires_at"],
    )

    op.create_table(
        "submission_attempts",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("authorization_id", sa.String(length=36), nullable=False),
        sa.Column("application_id", sa.String(length=255), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("vendor", sa.String(length=32), nullable=False),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("browser_session_id", sa.String(length=255), nullable=False),
        sa.Column("document_url_sha256", sa.String(length=64), nullable=False),
        sa.Column("submit_selector", sa.Text(), nullable=False),
        sa.Column("submit_control_sha256", sa.String(length=64), nullable=False),
        sa.Column("audit_run_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "submit_invoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("receipt_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("successful_submission_key", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["submit_authorizations.authorization_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("authorization_id"),
        sa.UniqueConstraint("successful_submission_key"),
    )
    op.create_index(
        op.f("ix_submission_attempts_authorization_id"),
        "submission_attempts",
        ["authorization_id"],
    )
    op.create_index(
        op.f("ix_submission_attempts_application_id"),
        "submission_attempts",
        ["application_id"],
    )
    op.create_index(
        op.f("ix_submission_attempts_job_id"),
        "submission_attempts",
        ["job_id"],
    )
    op.create_index(
        op.f("ix_submission_attempts_vendor"),
        "submission_attempts",
        ["vendor"],
    )
    op.create_index(
        op.f("ix_submission_attempts_browser_session_id"),
        "submission_attempts",
        ["browser_session_id"],
    )
    op.create_index(
        op.f("ix_submission_attempts_audit_run_id"),
        "submission_attempts",
        ["audit_run_id"],
    )
    op.create_index(
        op.f("ix_submission_attempts_status"),
        "submission_attempts",
        ["status"],
    )
    op.create_index(
        op.f("ix_submission_attempts_started_at"),
        "submission_attempts",
        ["started_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_submission_attempts_started_at"), table_name="submission_attempts")
    op.drop_index(op.f("ix_submission_attempts_status"), table_name="submission_attempts")
    op.drop_index(op.f("ix_submission_attempts_audit_run_id"), table_name="submission_attempts")
    op.drop_index(
        op.f("ix_submission_attempts_browser_session_id"),
        table_name="submission_attempts",
    )
    op.drop_index(op.f("ix_submission_attempts_vendor"), table_name="submission_attempts")
    op.drop_index(op.f("ix_submission_attempts_job_id"), table_name="submission_attempts")
    op.drop_index(op.f("ix_submission_attempts_application_id"), table_name="submission_attempts")
    op.drop_index(
        op.f("ix_submission_attempts_authorization_id"),
        table_name="submission_attempts",
    )
    op.drop_table("submission_attempts")

    op.drop_index(op.f("ix_submit_authorizations_expires_at"), table_name="submit_authorizations")
    op.drop_index(op.f("ix_submit_authorizations_created_at"), table_name="submit_authorizations")
    op.drop_index(op.f("ix_submit_authorizations_attempt_id"), table_name="submit_authorizations")
    op.drop_index(op.f("ix_submit_authorizations_status"), table_name="submit_authorizations")
    op.drop_index(
        op.f("ix_submit_authorizations_browser_session_id"),
        table_name="submit_authorizations",
    )
    op.drop_index(op.f("ix_submit_authorizations_audit_run_id"), table_name="submit_authorizations")
    op.drop_index(op.f("ix_submit_authorizations_vendor"), table_name="submit_authorizations")
    op.drop_index(op.f("ix_submit_authorizations_job_id"), table_name="submit_authorizations")
    op.drop_index(
        op.f("ix_submit_authorizations_application_id"),
        table_name="submit_authorizations",
    )
    op.drop_table("submit_authorizations")

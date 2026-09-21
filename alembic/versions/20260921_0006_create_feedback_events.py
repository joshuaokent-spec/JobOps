"""Create immutable feedback event stream.

Revision ID: 20260921_0006
Revises: 20260916_0005
Create Date: 2026-09-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0006"
down_revision: str | Sequence[str] | None = "20260916_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("application_id", sa.String(length=255), nullable=True),
        sa.Column("candidate_id", sa.String(length=255), nullable=True),
        sa.Column("resume_family_id", sa.String(length=100), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("model_version", sa.String(length=200), nullable=True),
        sa.Column("experiment_id", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in (
        "event_type",
        "job_id",
        "application_id",
        "candidate_id",
        "resume_family_id",
        "occurred_at",
        "observed_at",
        "source",
        "idempotency_key",
        "model_name",
        "experiment_id",
    ):
        op.create_index(op.f(f"ix_feedback_events_{column}"), "feedback_events", [column])

    op.create_index(
        "ix_feedback_events_job_occurred",
        "feedback_events",
        ["job_id", "occurred_at", "observed_at", "event_id"],
    )
    op.create_index(
        "ix_feedback_events_application_occurred",
        "feedback_events",
        ["application_id", "occurred_at", "observed_at", "event_id"],
    )
    op.create_index(
        "ix_feedback_events_type_occurred",
        "feedback_events",
        ["event_type", "occurred_at", "observed_at", "event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_events_type_occurred", table_name="feedback_events")
    op.drop_index("ix_feedback_events_application_occurred", table_name="feedback_events")
    op.drop_index("ix_feedback_events_job_occurred", table_name="feedback_events")
    for column in reversed(
        (
            "event_type",
            "job_id",
            "application_id",
            "candidate_id",
            "resume_family_id",
            "occurred_at",
            "observed_at",
            "source",
            "idempotency_key",
            "model_name",
            "experiment_id",
        )
    ):
        op.drop_index(op.f(f"ix_feedback_events_{column}"), table_name="feedback_events")
    op.drop_table("feedback_events")

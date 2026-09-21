"""Create flagship readiness snapshots.

Revision ID: 20260921_0008
Revises: 20260921_0007
Create Date: 2026-09-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0008"
down_revision: str | Sequence[str] | None = "20260921_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flagship_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("candidate_id", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_examined", sa.Integer(), nullable=False),
        sa.Column("total_hard_eligible", sa.Integer(), nullable=False),
        sa.Column("total_hard_rejected", sa.Integer(), nullable=False),
        sa.Column("total_fit_eligible", sa.Integer(), nullable=False),
        sa.Column("total_fit_rejected", sa.Integer(), nullable=False),
        sa.Column("prepared_count", sa.Integer(), nullable=False),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("review_required_count", sa.Integer(), nullable=False),
        sa.Column("rejection_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["search_profiles.profile_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    for column in ("profile_id", "candidate_id", "started_at", "completed_at", "created_at"):
        op.create_index(op.f(f"ix_flagship_runs_{column}"), "flagship_runs", [column])

    op.create_table(
        "flagship_prepared_jobs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("resume_family_id", sa.String(length=100), nullable=False),
        sa.Column("resume_selection_score", sa.Float(), nullable=False),
        sa.Column("resume_low_confidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("readiness", sa.String(length=32), nullable=False),
        sa.Column("readiness_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["flagship_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "job_id"),
    )
    for column in ("job_id", "resume_family_id", "readiness"):
        op.create_index(
            op.f(f"ix_flagship_prepared_jobs_{column}"),
            "flagship_prepared_jobs",
            [column],
        )


def downgrade() -> None:
    for column in reversed(("job_id", "resume_family_id", "readiness")):
        op.drop_index(
            op.f(f"ix_flagship_prepared_jobs_{column}"),
            table_name="flagship_prepared_jobs",
        )
    op.drop_table("flagship_prepared_jobs")

    for column in reversed(("profile_id", "candidate_id", "started_at", "completed_at", "created_at")):
        op.drop_index(op.f(f"ix_flagship_runs_{column}"), table_name="flagship_runs")
    op.drop_table("flagship_runs")

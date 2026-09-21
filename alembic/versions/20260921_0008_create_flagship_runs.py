"""Create durable flagship run readiness snapshots.

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
    op.create_index(op.f("ix_flagship_runs_profile_id"), "flagship_runs", ["profile_id"])
    op.create_index(
        op.f("ix_flagship_runs_candidate_id"),
        "flagship_runs",
        ["candidate_id"],
    )
    op.create_index(
        op.f("ix_flagship_runs_completed_at"),
        "flagship_runs",
        ["completed_at"],
    )

    op.create_table(
        "flagship_run_jobs",
        sa.Column("run_job_id", sa.String(length=320), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("family_id", sa.String(length=100), nullable=False),
        sa.Column("family_score", sa.Float(), nullable=False),
        sa.Column("readiness", sa.String(length=32), nullable=False),
        sa.Column("readiness_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["flagship_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_job_id"),
    )
    op.create_index(
        op.f("ix_flagship_run_jobs_run_id"),
        "flagship_run_jobs",
        ["run_id"],
    )
    op.create_index(
        op.f("ix_flagship_run_jobs_job_id"),
        "flagship_run_jobs",
        ["job_id"],
    )
    op.create_index(
        op.f("ix_flagship_run_jobs_readiness"),
        "flagship_run_jobs",
        ["readiness"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_flagship_run_jobs_readiness"),
        table_name="flagship_run_jobs",
    )
    op.drop_index(op.f("ix_flagship_run_jobs_job_id"), table_name="flagship_run_jobs")
    op.drop_index(op.f("ix_flagship_run_jobs_run_id"), table_name="flagship_run_jobs")
    op.drop_table("flagship_run_jobs")
    op.drop_index(op.f("ix_flagship_runs_completed_at"), table_name="flagship_runs")
    op.drop_index(op.f("ix_flagship_runs_candidate_id"), table_name="flagship_runs")
    op.drop_index(op.f("ix_flagship_runs_profile_id"), table_name="flagship_runs")
    op.drop_table("flagship_runs")

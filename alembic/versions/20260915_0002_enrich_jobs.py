"""Enrich canonical jobs for normalization and deduplication.

Revision ID: 20260915_0002
Revises: 20260915_0001
Create Date: 2026-09-15
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260915_0002"
down_revision: str | Sequence[str] | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("employment_type", sa.String(length=100), nullable=True))
    op.add_column("jobs", sa.Column("salary_currency", sa.String(length=12), nullable=True))
    op.add_column("jobs", sa.Column("salary_interval", sa.String(length=32), nullable=True))
    op.add_column("jobs", sa.Column("source_job_id", sa.String(length=255), nullable=True))
    op.add_column("jobs", sa.Column("apply_url", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    op.add_column("jobs", sa.Column("source_metadata", sa.JSON(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(op.f("ix_jobs_active"), "jobs", ["active"], unique=False)
    op.create_index(op.f("ix_jobs_dedupe_key"), "jobs", ["dedupe_key"], unique=False)
    op.create_index(op.f("ix_jobs_employment_type"), "jobs", ["employment_type"], unique=False)
    op.create_index(op.f("ix_jobs_source_job_id"), "jobs", ["source_job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_source_job_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_employment_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_dedupe_key"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_active"), table_name="jobs")
    op.drop_column("jobs", "active")
    op.drop_column("jobs", "source_metadata")
    op.drop_column("jobs", "dedupe_key")
    op.drop_column("jobs", "source_updated_at")
    op.drop_column("jobs", "apply_url")
    op.drop_column("jobs", "source_job_id")
    op.drop_column("jobs", "salary_interval")
    op.drop_column("jobs", "salary_currency")
    op.drop_column("jobs", "employment_type")

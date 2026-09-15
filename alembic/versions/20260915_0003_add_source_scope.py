"""Add source scope for safe feed refreshes.

Revision ID: 20260915_0003
Revises: 20260915_0002
Create Date: 2026-09-15
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260915_0003"
down_revision: str | Sequence[str] | None = "20260915_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("source_scope", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_jobs_source_scope"),
        "jobs",
        ["source_scope"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_source_scope_active",
        "jobs",
        ["source", "source_scope", "active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_source_scope_active", table_name="jobs")
    op.drop_index(op.f("ix_jobs_source_scope"), table_name="jobs")
    op.drop_column("jobs", "source_scope")

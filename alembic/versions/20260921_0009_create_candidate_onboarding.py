"""Create candidate onboarding storage.

Revision ID: 20260921_0009
Revises: 20260921_0008
Create Date: 2026-09-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0009"
down_revision: str | Sequence[str] | None = "20260921_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_onboarding",
        sa.Column("candidate_id", sa.String(length=255), nullable=False),
        sa.Column("candidate_profile", sa.JSON(), nullable=False),
        sa.Column("resume_evidence", sa.JSON(), nullable=False),
        sa.Column("resume_assets", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("run_defaults", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_index(
        op.f("ix_candidate_onboarding_updated_at"),
        "candidate_onboarding",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_candidate_onboarding_updated_at"),
        table_name="candidate_onboarding",
    )
    op.drop_table("candidate_onboarding")

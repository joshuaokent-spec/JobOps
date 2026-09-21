"""Create persistent flagship search profiles.

Revision ID: 20260921_0007
Revises: 20260921_0006
Create Date: 2026-09-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0007"
down_revision: str | Sequence[str] | None = "20260921_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_profiles",
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("candidate_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role_queries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("required_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("excluded_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_work_modes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("locations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("employment_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("minimum_salary", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column(
            "salary_floor_policy",
            sa.String(length=32),
            nullable=False,
            server_default="minimum_offered",
        ),
        sa.Column(
            "unknown_compensation_policy",
            sa.String(length=16),
            nullable=False,
            server_default="exclude",
        ),
        sa.Column("excluded_companies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("minimum_fit_score", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_index(
        op.f("ix_search_profiles_candidate_id"),
        "search_profiles",
        ["candidate_id"],
    )
    op.create_index(
        op.f("ix_search_profiles_active"),
        "search_profiles",
        ["active"],
    )
    op.create_index(
        op.f("ix_search_profiles_created_at"),
        "search_profiles",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_search_profiles_created_at"), table_name="search_profiles")
    op.drop_index(op.f("ix_search_profiles_active"), table_name="search_profiles")
    op.drop_index(op.f("ix_search_profiles_candidate_id"), table_name="search_profiles")
    op.drop_table("search_profiles")

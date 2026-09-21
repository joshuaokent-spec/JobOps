"""Add hybrid location-radius hubs to search profiles.

Revision ID: 20260921_0010
Revises: 20260921_0009
Create Date: 2026-09-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0010"
down_revision: str | Sequence[str] | None = "20260921_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_profiles",
        sa.Column(
            "hybrid_location_hubs",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("search_profiles", "hybrid_location_hubs")

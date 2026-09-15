"""Create persistent human approval queue.

Revision ID: 20260915_0004
Revises: 20260915_0003
Create Date: 2026-09-15
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260915_0004"
down_revision: str | Sequence[str] | None = "20260915_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_items",
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=255), nullable=False),
        sa.Column("family_id", sa.String(length=100), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("route", sa.String(length=40), nullable=False),
        sa.Column("review_band", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("proposed_answer", sa.Text(), nullable=True),
        sa.Column("edited_answer", sa.Text(), nullable=True),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=16), nullable=True),
        sa.Column("verification_findings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reviewer", sa.String(length=200), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(op.f("ix_approval_items_job_id"), "approval_items", ["job_id"])
    op.create_index(op.f("ix_approval_items_family_id"), "approval_items", ["family_id"])
    op.create_index(op.f("ix_approval_items_category"), "approval_items", ["category"])
    op.create_index(op.f("ix_approval_items_review_band"), "approval_items", ["review_band"])
    op.create_index(op.f("ix_approval_items_reason"), "approval_items", ["reason"])
    op.create_index(op.f("ix_approval_items_status"), "approval_items", ["status"])
    op.create_index(op.f("ix_approval_items_created_at"), "approval_items", ["created_at"])
    op.create_index(
        "ix_approval_items_status_created_at",
        "approval_items",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_items_status_created_at", table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_created_at"), table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_status"), table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_reason"), table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_review_band"), table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_category"), table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_family_id"), table_name="approval_items")
    op.drop_index(op.f("ix_approval_items_job_id"), table_name="approval_items")
    op.drop_table("approval_items")

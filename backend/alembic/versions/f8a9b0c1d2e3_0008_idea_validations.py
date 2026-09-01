"""0008_idea_validations

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-01

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idea_validations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idea_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column("planned_evidence", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY', 'RUNNING', 'COMPLETED', 'CANCELLED')",
            name="idea_validation_status",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('PASS', 'PARTIAL', 'FAIL', 'INCONCLUSIVE')",
            name="idea_validation_outcome",
        ),
        sa.CheckConstraint(
            "("
            "  (status = 'COMPLETED' AND outcome IS NOT NULL AND result_summary IS NOT NULL AND completed_at IS NOT NULL)"
            "  OR"
            "  (status <> 'COMPLETED' AND outcome IS NULL)"
            ")",
            name="idea_validation_completed_invariant",
        ),
        sa.CheckConstraint(
            "("
            "  (status = 'RUNNING' AND started_at IS NOT NULL)"
            "  OR"
            "  (status IN ('DRAFT', 'READY') AND started_at IS NULL AND completed_at IS NULL)"
            "  OR"
            "  (status IN ('COMPLETED', 'CANCELLED'))"
            ")",
            name="idea_validation_timing_invariant",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_idea_validations_idea_id", "idea_validations", ["idea_id"])
    op.create_index("ix_idea_validations_created_by", "idea_validations", ["created_by"])
    op.create_index("ix_idea_validations_status", "idea_validations", ["status"])
    op.create_index(
        "ix_idea_validations_idea_created",
        "idea_validations",
        ["idea_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idea_validations_idea_created", table_name="idea_validations")
    op.drop_index("ix_idea_validations_status", table_name="idea_validations")
    op.drop_index("ix_idea_validations_created_by", table_name="idea_validations")
    op.drop_index("ix_idea_validations_idea_id", table_name="idea_validations")
    op.drop_table("idea_validations")

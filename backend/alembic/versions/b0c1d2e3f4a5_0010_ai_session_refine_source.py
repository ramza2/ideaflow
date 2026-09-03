"""0010_ai_session_refine_source

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-09-03

Step 17: REFINE source linkage + REFINE_IDEA job type.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "idea_ai_sessions",
        sa.Column("source_idea_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "idea_ai_sessions",
        sa.Column("source_idea_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "idea_ai_sessions",
        sa.Column(
            "source_idea_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "idea_ai_sessions",
        sa.Column("refine_direction", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_idea_ai_sessions_source_idea_id_ideas",
        "idea_ai_sessions",
        "ideas",
        ["source_idea_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_idea_ai_sessions_source_idea_id",
        "idea_ai_sessions",
        ["source_idea_id"],
        unique=False,
    )
    op.create_check_constraint(
        "idea_ai_session_refine_direction",
        "idea_ai_sessions",
        "refine_direction IS NULL OR refine_direction IN ("
        "'EXPAND_DETAIL', 'TECHNICAL_IMPLEMENTATION', 'BUSINESS_PERSPECTIVE', "
        "'USER_PERSPECTIVE', 'COUNTER_PERSPECTIVE', 'RISK_ANALYSIS', "
        "'MINIMUM_VALIDATION', 'NEXT_ACTIONS')",
    )

    op.drop_constraint("ai_job_research_run_type", "ai_jobs", type_="check")
    op.drop_constraint("ai_job_type", "ai_jobs", type_="check")
    op.create_check_constraint(
        "ai_job_type",
        "ai_jobs",
        "job_type IN ('STRUCTURE_IDEA', 'REFINE_IDEA', 'WEB_RESEARCH')",
    )
    op.create_check_constraint(
        "ai_job_research_run_type",
        "ai_jobs",
        "(job_type IN ('STRUCTURE_IDEA', 'REFINE_IDEA') AND research_run_id IS NULL) OR "
        "(job_type = 'WEB_RESEARCH' AND research_run_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ai_job_research_run_type", "ai_jobs", type_="check")
    op.drop_constraint("ai_job_type", "ai_jobs", type_="check")
    op.create_check_constraint(
        "ai_job_type",
        "ai_jobs",
        "job_type IN ('STRUCTURE_IDEA', 'WEB_RESEARCH')",
    )
    op.create_check_constraint(
        "ai_job_research_run_type",
        "ai_jobs",
        "(job_type = 'STRUCTURE_IDEA' AND research_run_id IS NULL) OR "
        "(job_type = 'WEB_RESEARCH' AND research_run_id IS NOT NULL)",
    )

    op.drop_constraint("idea_ai_session_refine_direction", "idea_ai_sessions", type_="check")
    op.drop_index("ix_idea_ai_sessions_source_idea_id", table_name="idea_ai_sessions")
    op.drop_constraint(
        "fk_idea_ai_sessions_source_idea_id_ideas",
        "idea_ai_sessions",
        type_="foreignkey",
    )
    op.drop_column("idea_ai_sessions", "refine_direction")
    op.drop_column("idea_ai_sessions", "source_idea_snapshot")
    op.drop_column("idea_ai_sessions", "source_idea_updated_at")
    op.drop_column("idea_ai_sessions", "source_idea_id")

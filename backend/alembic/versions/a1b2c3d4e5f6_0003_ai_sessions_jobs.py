"""0003_ai_sessions_jobs

Revision ID: a1b2c3d4e5f6
Revises: 765468804dd6
Create Date: 2026-08-26 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "765468804dd6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idea_ai_sessions",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("requester_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), server_default="CREATE", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PROCESSING", nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("clarifying_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("clarification_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("draft_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("research_recommended", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("research_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confirmed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_idea_id", sa.UUID(), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.String(length=512), nullable=True),
        sa.Column("llm_provider", sa.String(length=64), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('CREATE', 'REFINE', 'RESEARCH')",
            name="idea_ai_session_purpose",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'PROCESSING', 'NEEDS_CLARIFICATION', 'READY_FOR_REVIEW', "
            "'CONFIRMED', 'FAILED', 'CANCELLED')",
            name="idea_ai_session_status",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_idea_ai_sessions_requester_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_idea_id"],
            ["ideas.id"],
            name=op.f("fk_idea_ai_sessions_result_idea_id_ideas"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_idea_ai_sessions_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idea_ai_sessions")),
    )
    op.create_index("ix_idea_ai_sessions_workspace_id", "idea_ai_sessions", ["workspace_id"])
    op.create_index("ix_idea_ai_sessions_requester_id", "idea_ai_sessions", ["requester_id"])
    op.create_index("ix_idea_ai_sessions_status", "idea_ai_sessions", ["status"])
    op.create_index("ix_idea_ai_sessions_result_idea_id", "idea_ai_sessions", ["result_idea_id"])

    op.create_table(
        "ai_jobs",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(length=32), server_default="STRUCTURE_IDEA", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="QUEUED", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("job_type IN ('STRUCTURE_IDEA')", name="ai_job_type"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ai_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["idea_ai_sessions.id"],
            name=op.f("fk_ai_jobs_session_id_idea_ai_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_jobs")),
    )
    op.create_index("ix_ai_jobs_session_id", "ai_jobs", ["session_id"])
    op.create_index("ix_ai_jobs_status_available_at", "ai_jobs", ["status", "available_at"])
    op.create_index("ix_ai_jobs_lease_until", "ai_jobs", ["lease_until"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_lease_until", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_status_available_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_session_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.drop_index("ix_idea_ai_sessions_result_idea_id", table_name="idea_ai_sessions")
    op.drop_index("ix_idea_ai_sessions_status", table_name="idea_ai_sessions")
    op.drop_index("ix_idea_ai_sessions_requester_id", table_name="idea_ai_sessions")
    op.drop_index("ix_idea_ai_sessions_workspace_id", table_name="idea_ai_sessions")
    op.drop_table("idea_ai_sessions")

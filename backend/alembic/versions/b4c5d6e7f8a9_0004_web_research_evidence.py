"""0004_web_research_evidence

Revision ID: b4c5d6e7f8a9
Revises: a1b2c3d4e5f6
Create Date: 2026-08-28 02:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_research_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("requester_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="AWAITING_APPROVAL", nullable=False),
        sa.Column("queries_to_send", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sanitization_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("base_draft_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("base_field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("user_edited_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("failure_phase", sa.String(length=32), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.String(length=512), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("research_summary", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(length=64), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ("
            "'AWAITING_APPROVAL', 'QUEUED', 'SEARCHING', 'REFINING', "
            "'READY', 'FAILED', 'CANCELLED')",
            name="web_research_run_status",
        ),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["idea_ai_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_web_research_runs_requester_id", "web_research_runs", ["requester_id"])
    op.create_index("ix_web_research_runs_session_id", "web_research_runs", ["session_id"])
    op.create_index("ix_web_research_runs_status", "web_research_runs", ["status"])

    op.create_table(
        "web_evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_run_id", sa.UUID(), nullable=False),
        sa.Column("query", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("snippet", sa.String(length=2000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("rank", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("related_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["web_research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_run_id", "url_hash", name="uq_web_evidence_run_url_hash"),
    )
    op.create_index("ix_web_evidence_research_run_id", "web_evidence", ["research_run_id"])

    op.add_column("ai_jobs", sa.Column("research_run_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_ai_jobs_research_run_id",
        "ai_jobs",
        "web_research_runs",
        ["research_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_ai_jobs_research_run_id", "ai_jobs", ["research_run_id"])

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


def downgrade() -> None:
    op.execute("DELETE FROM ai_jobs WHERE job_type = 'WEB_RESEARCH'")

    op.drop_constraint("ai_job_research_run_type", "ai_jobs", type_="check")
    op.drop_constraint("ai_job_type", "ai_jobs", type_="check")
    op.create_check_constraint(
        "ai_job_type",
        "ai_jobs",
        "job_type IN ('STRUCTURE_IDEA')",
    )
    op.drop_index("ix_ai_jobs_research_run_id", table_name="ai_jobs")
    op.drop_constraint("fk_ai_jobs_research_run_id", "ai_jobs", type_="foreignkey")
    op.drop_column("ai_jobs", "research_run_id")

    op.drop_index("ix_web_evidence_research_run_id", table_name="web_evidence")
    op.drop_table("web_evidence")

    op.drop_index("ix_web_research_runs_status", table_name="web_research_runs")
    op.drop_index("ix_web_research_runs_session_id", table_name="web_research_runs")
    op.drop_index("ix_web_research_runs_requester_id", table_name="web_research_runs")
    op.drop_table("web_research_runs")

"""0005_review_comment_notification

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-28 06:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idea_review_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("idea_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="OPEN", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=True),
        sa.Column("completion_note", sa.Text(), nullable=True),
        sa.Column("suggested_next_review_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('GENERAL', 'NEEDS_INFO', 'NEXT_STAGE')",
            name="idea_review_request_kind",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'COMPLETED', 'CANCELLED')",
            name="idea_review_request_status",
        ),
        sa.CheckConstraint(
            "result IS NULL OR result IN ("
            "'ADVANCE_RECOMMENDED', 'KEEP', 'HOLD', 'NEEDS_INFO')",
            name="idea_review_request_result",
        ),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_workspace", "idea_review_requests", ["workspace_id"])
    op.create_index("ix_review_idea", "idea_review_requests", ["idea_id"])
    op.create_index(
        "ix_review_reviewer_status",
        "idea_review_requests",
        ["reviewer_id", "status"],
    )
    op.create_index("ix_review_requested_by", "idea_review_requests", ["requested_by"])
    op.create_index("ix_review_due_date", "idea_review_requests", ["due_date"])
    op.create_index(
        "uq_review_open_idea_reviewer",
        "idea_review_requests",
        ["idea_id", "reviewer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )

    op.create_table(
        "idea_comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("idea_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_idea_created", "idea_comments", ["idea_id", "created_at"])
    op.create_index("ix_comments_author", "idea_comments", ["author_id"])

    op.create_table(
        "idea_comment_mentions",
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["idea_comments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("comment_id", "user_id"),
    )
    op.create_index("ix_comment_mentions_user", "idea_comment_mentions", ["user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("idea_id", sa.UUID(), nullable=True),
        sa.Column("comment_id", sa.UUID(), nullable=True),
        sa.Column("review_request_id", sa.UUID(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "type IN ("
            "'REVIEW_REQUESTED', 'REVIEW_COMPLETED', 'COMMENT_ADDED', "
            "'MENTION', 'ASSIGNED')",
            name="notification_type",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["comment_id"], ["idea_comments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_request_id"], ["idea_review_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipient_id", "dedupe_key", name="uq_notification_dedupe"),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_recipient_read",
        "notifications",
        ["recipient_id", "read_at"],
    )
    op.create_index(
        "ix_notifications_workspace_recipient",
        "notifications",
        ["workspace_id", "recipient_id"],
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("idea_comment_mentions")
    op.drop_table("idea_comments")
    op.drop_index("uq_review_open_idea_reviewer", table_name="idea_review_requests")
    op.drop_table("idea_review_requests")

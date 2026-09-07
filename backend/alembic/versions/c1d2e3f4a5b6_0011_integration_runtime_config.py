"""0011_integration_runtime_config

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-09-04 06:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_runtime_configs",
        sa.Column("integration_key", sa.String(length=32), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("secret_mode", sa.String(length=32), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.UUID(), nullable=True),
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
            "integration_key IN ('LLM', 'WEB_SEARCH', 'EMBEDDING')",
            name="integration_runtime_config_key",
        ),
        sa.CheckConstraint(
            "secret_mode IN ('INHERIT_ENV', 'ENCRYPTED', 'CLEARED')",
            name="integration_runtime_config_secret_mode",
        ),
        sa.CheckConstraint(
            "(secret_mode = 'ENCRYPTED' AND secret_ciphertext IS NOT NULL) OR "
            "(secret_mode <> 'ENCRYPTED' AND secret_ciphertext IS NULL)",
            name="integration_runtime_config_secret_consistency",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("integration_key"),
    )

    op.create_table(
        "integration_config_audits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("integration_key", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "integration_key IN ('LLM', 'WEB_SEARCH', 'EMBEDDING')",
            name="integration_config_audit_key",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_integration_config_audits_integration_key",
        "integration_config_audits",
        ["integration_key"],
    )
    op.create_index(
        "ix_integration_config_audits_created_at",
        "integration_config_audits",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_config_audits_created_at", table_name="integration_config_audits")
    op.drop_index(
        "ix_integration_config_audits_integration_key",
        table_name="integration_config_audits",
    )
    op.drop_table("integration_config_audits")
    op.drop_table("integration_runtime_configs")

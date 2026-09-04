"""Runtime Integration Config ORM models (Step 17.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IntegrationRuntimeConfig(TimestampMixin, Base):
    __tablename__ = "integration_runtime_configs"
    __table_args__ = (
        CheckConstraint(
            "integration_key IN ('LLM', 'WEB_SEARCH', 'EMBEDDING')",
            name="integration_runtime_config_key",
        ),
        CheckConstraint(
            "secret_mode IN ('INHERIT_ENV', 'ENCRYPTED', 'CLEARED')",
            name="integration_runtime_config_secret_mode",
        ),
        CheckConstraint(
            "(secret_mode = 'ENCRYPTED' AND secret_ciphertext IS NOT NULL) OR "
            "(secret_mode <> 'ENCRYPTED' AND secret_ciphertext IS NULL)",
            name="integration_runtime_config_secret_consistency",
        ),
    )

    integration_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    secret_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="INHERIT_ENV")
    secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class IntegrationConfigAudit(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "integration_config_audits"
    __table_args__ = (
        CheckConstraint(
            "integration_key IN ('LLM', 'WEB_SEARCH', 'EMBEDDING')",
            name="integration_config_audit_key",
        ),
    )

    integration_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_fields: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

"""SystemSetting ORM model (Step 11)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint(
            "key IN ("
            "'GLOBAL_LLM_ENABLED', 'GLOBAL_WEB_SEARCH_ENABLED', "
            "'DEFAULT_TEAM_ALLOW_LLM', 'DEFAULT_TEAM_ALLOW_WEB_SEARCH'"
            ")",
            name="system_setting_key",
        ),
    )

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

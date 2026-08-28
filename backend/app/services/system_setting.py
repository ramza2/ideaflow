"""SystemSetting service (Step 11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import SystemSettingKey
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.workspace import Workspace

_DEFAULTS: dict[SystemSettingKey, bool] = {
    SystemSettingKey.GLOBAL_LLM_ENABLED: True,
    SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED: True,
    SystemSettingKey.DEFAULT_TEAM_ALLOW_LLM: True,
    SystemSettingKey.DEFAULT_TEAM_ALLOW_WEB_SEARCH: True,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SettingValue:
    value: bool
    source: str
    updated_at: datetime | None
    updated_by: User | None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise AppError("Invalid setting value.", code="INVALID_SETTING_VALUE", status_code=400)


def get_setting_row(db: Session, key: SystemSettingKey) -> SystemSetting | None:
    return db.get(SystemSetting, key.value)


def get_bool_setting(db: Session, key: SystemSettingKey) -> bool:
    row = get_setting_row(db, key)
    if row is None:
        return _DEFAULTS[key]
    return _coerce_bool(row.value_json)


def get_setting_value(db: Session, key: SystemSettingKey) -> SettingValue:
    row = get_setting_row(db, key)
    if row is None:
        return SettingValue(
            value=_DEFAULTS[key],
            source="DEFAULT",
            updated_at=None,
            updated_by=None,
        )
    updated_by = db.get(User, row.updated_by) if row.updated_by else None
    return SettingValue(
        value=_coerce_bool(row.value_json),
        source="DATABASE",
        updated_at=row.updated_at,
        updated_by=updated_by,
    )


def get_all_settings(db: Session) -> dict[SystemSettingKey, SettingValue]:
    return {key: get_setting_value(db, key) for key in SystemSettingKey}


def update_settings(
    db: Session,
    *,
    actor_id: UUID,
    updates: dict[SystemSettingKey, bool],
) -> dict[SystemSettingKey, SettingValue]:
    now = utcnow()
    for key, value in updates.items():
        if not isinstance(value, bool):
            raise AppError("Invalid setting value.", code="INVALID_SETTING_VALUE", status_code=400)
        row = get_setting_row(db, key)
        if row is None:
            row = SystemSetting(
                key=key.value,
                value_json=value,
                updated_by=actor_id,
                updated_at=now,
            )
            db.add(row)
        else:
            row.value_json = value
            row.updated_by = actor_id
            row.updated_at = now
    db.flush()
    return get_all_settings(db)


def effective_allow_llm(db: Session, workspace: Workspace) -> bool:
    return bool(workspace.allow_llm and get_bool_setting(db, SystemSettingKey.GLOBAL_LLM_ENABLED))


def effective_allow_web_search(db: Session, workspace: Workspace) -> bool:
    return bool(
        workspace.allow_web_search
        and workspace.allow_llm
        and get_bool_setting(db, SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED)
        and get_bool_setting(db, SystemSettingKey.GLOBAL_LLM_ENABLED)
    )


def require_global_llm_enabled(db: Session) -> None:
    if not get_bool_setting(db, SystemSettingKey.GLOBAL_LLM_ENABLED):
        raise AppError(
            "시스템 정책에 의해 AI 기능이 비활성화되어 있습니다.",
            code="SYSTEM_LLM_DISABLED",
            status_code=403,
        )


def require_global_web_search_enabled(db: Session) -> None:
    if not get_bool_setting(db, SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED):
        raise AppError(
            "시스템 정책에 의해 웹 검색 기능이 비활성화되어 있습니다.",
            code="SYSTEM_WEB_SEARCH_DISABLED",
            status_code=403,
        )

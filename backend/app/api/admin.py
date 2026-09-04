"""Admin HTTP endpoints (Step 11 / Step 17.6)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf, require_system_admin
from app.core.errors import AppError
from app.db.session import get_db
from app.models.enums import IntegrationKey, SystemSettingKey
from app.schemas.admin import (
    AdminIntegrationConfigResponse,
    AdminPasswordResetRequest,
    AdminUserCreateRequest,
    AdminUserListResponse,
    AdminUserPublic,
    AdminUserUpdateRequest,
    EmbeddingConnectionTestResult,
    EmbeddingIntegrationUpdateRequest,
    IntegrationConfigAuditListResponse,
    LlmConnectionTestResult,
    LlmIntegrationUpdateRequest,
    RuntimeResetRequest,
    SettingMetadata,
    SystemSettingsResponse,
    SystemSettingsUpdateRequest,
    WebSearchConnectionTestRequest,
    WebSearchConnectionTestResult,
    WebSearchIntegrationUpdateRequest,
)
from app.models.user import User
from app.services import admin_integration as admin_integration_service
from app.services import admin_user as admin_user_service
from app.services import system_setting as system_setting_service
from app.services.integration_runtime_config import (
    reset_runtime_config,
    upsert_runtime_config,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_UPDATE_META_KEYS = frozenset({"expected_revision", "api_key_action", "api_key"})


def _patch_fields_from_update(body: Any) -> tuple[dict[str, Any], str, str | None, int]:
    # exclude_unset keeps explicit nulls (e.g. enable_thinking: null) in the patch.
    data = body.model_dump(exclude_unset=True)
    expected_revision = int(data.pop("expected_revision"))
    api_key_action = str(data.pop("api_key_action", "KEEP"))
    api_key = data.pop("api_key", None)
    patch_fields = {k: v for k, v in data.items() if k not in _UPDATE_META_KEYS}
    return patch_fields, api_key_action, api_key, expected_revision


def _parse_integration_key(value: str | None) -> IntegrationKey | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().upper()
    try:
        return IntegrationKey(normalized)
    except ValueError as exc:
        raise AppError(
            "알 수 없는 integration 키입니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        ) from exc


def _settings_response(db: Session) -> SystemSettingsResponse:
    all_settings = system_setting_service.get_all_settings(db)
    metadata: dict[str, SettingMetadata] = {}
    for key, item in all_settings.items():
        metadata[key.value] = SettingMetadata(
            source=item.source,
            updated_at=item.updated_at,
            updated_by=(
                {"id": item.updated_by.id, "name": item.updated_by.name}
                if item.updated_by
                else None
            ),
        )
    return SystemSettingsResponse(
        global_llm_enabled=all_settings[SystemSettingKey.GLOBAL_LLM_ENABLED].value,
        global_web_search_enabled=all_settings[SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED].value,
        default_team_allow_llm=all_settings[SystemSettingKey.DEFAULT_TEAM_ALLOW_LLM].value,
        default_team_allow_web_search=all_settings[
            SystemSettingKey.DEFAULT_TEAM_ALLOW_WEB_SEARCH
        ].value,
        metadata=metadata,
    )


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_system_admin)],
    q: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    system_role: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserListResponse:
    items, total = admin_user_service.list_users(
        db,
        current_user_id=admin.id,
        q=q,
        status=status,
        system_role=system_role,
        limit=limit,
        offset=offset,
    )
    return AdminUserListResponse(items=items, total=total)


@router.post("/users", response_model=AdminUserPublic, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminUserPublic:
    del auth
    result = admin_user_service.create_user(db, actor_id=admin.id, payload=body)
    db.commit()
    return result


@router.patch("/users/{user_id}", response_model=AdminUserPublic)
def update_user(
    user_id: UUID,
    body: AdminUserUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminUserPublic:
    del auth
    result = admin_user_service.update_user(
        db, actor_id=admin.id, user_id=user_id, payload=body
    )
    db.commit()
    return result


@router.post("/users/{user_id}/reset-password", response_model=AdminUserPublic)
def reset_password(
    user_id: UUID,
    body: AdminPasswordResetRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminUserPublic:
    del auth
    result = admin_user_service.reset_password(
        db,
        actor_id=admin.id,
        user_id=user_id,
        temporary_password=body.temporary_password,
    )
    db.commit()
    return result


@router.post("/users/{user_id}/unlock-login", response_model=AdminUserPublic)
def unlock_login(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminUserPublic:
    del auth
    result = admin_user_service.unlock_login(
        db, actor_id=admin.id, user_id=user_id
    )
    db.commit()
    return result


@router.get("/system-settings", response_model=SystemSettingsResponse)
def get_system_settings(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> SystemSettingsResponse:
    del admin
    return _settings_response(db)


@router.patch("/system-settings", response_model=SystemSettingsResponse)
def patch_system_settings(
    body: SystemSettingsUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> SystemSettingsResponse:
    del auth
    updates: dict[SystemSettingKey, bool] = {}
    if body.global_llm_enabled is not None:
        updates[SystemSettingKey.GLOBAL_LLM_ENABLED] = body.global_llm_enabled
    if body.global_web_search_enabled is not None:
        updates[SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED] = body.global_web_search_enabled
    if body.default_team_allow_llm is not None:
        updates[SystemSettingKey.DEFAULT_TEAM_ALLOW_LLM] = body.default_team_allow_llm
    if body.default_team_allow_web_search is not None:
        updates[SystemSettingKey.DEFAULT_TEAM_ALLOW_WEB_SEARCH] = body.default_team_allow_web_search
    if updates:
        system_setting_service.update_settings(
            db, actor_id=admin.id, updates=updates
        )
        db.commit()
    return _settings_response(db)


@router.get("/integrations", response_model=AdminIntegrationConfigResponse)
def get_integrations(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del admin
    return admin_integration_service.get_integration_config(db)


@router.patch("/integrations/llm", response_model=AdminIntegrationConfigResponse)
def patch_llm_integration(
    body: LlmIntegrationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del auth
    patch_fields, api_key_action, api_key, expected_revision = _patch_fields_from_update(body)
    upsert_runtime_config(
        db,
        key=IntegrationKey.LLM,
        actor_id=admin.id,
        expected_revision=expected_revision,
        patch_fields=patch_fields,
        api_key_action=api_key_action,
        api_key=api_key,
    )
    db.commit()
    return admin_integration_service.get_integration_config(db)


@router.patch("/integrations/web-search", response_model=AdminIntegrationConfigResponse)
def patch_web_search_integration(
    body: WebSearchIntegrationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del auth
    patch_fields, api_key_action, api_key, expected_revision = _patch_fields_from_update(body)
    upsert_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=expected_revision,
        patch_fields=patch_fields,
        api_key_action=api_key_action,
        api_key=api_key,
    )
    db.commit()
    return admin_integration_service.get_integration_config(db)


@router.patch("/integrations/embedding", response_model=AdminIntegrationConfigResponse)
def patch_embedding_integration(
    body: EmbeddingIntegrationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del auth
    patch_fields, api_key_action, api_key, expected_revision = _patch_fields_from_update(body)
    upsert_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=expected_revision,
        patch_fields=patch_fields,
        api_key_action=api_key_action,
        api_key=api_key,
    )
    db.commit()
    return admin_integration_service.get_integration_config(db)


@router.delete("/integrations/llm/runtime-config", response_model=AdminIntegrationConfigResponse)
def reset_llm_runtime_config(
    body: RuntimeResetRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del auth
    reset_runtime_config(
        db,
        key=IntegrationKey.LLM,
        actor_id=admin.id,
        expected_revision=body.expected_revision,
    )
    db.commit()
    return admin_integration_service.get_integration_config(db)


@router.delete(
    "/integrations/web-search/runtime-config",
    response_model=AdminIntegrationConfigResponse,
)
def reset_web_search_runtime_config(
    body: RuntimeResetRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del auth
    reset_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=body.expected_revision,
    )
    db.commit()
    return admin_integration_service.get_integration_config(db)


@router.delete(
    "/integrations/embedding/runtime-config",
    response_model=AdminIntegrationConfigResponse,
)
def reset_embedding_runtime_config(
    body: RuntimeResetRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> AdminIntegrationConfigResponse:
    del auth
    reset_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=body.expected_revision,
    )
    db.commit()
    return admin_integration_service.get_integration_config(db)


@router.get(
    "/integrations/config-audit",
    response_model=IntegrationConfigAuditListResponse,
)
def list_integration_config_audit(
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[User, Depends(require_system_admin)],
    integration: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> IntegrationConfigAuditListResponse:
    del admin
    key = _parse_integration_key(integration)
    return admin_integration_service.get_config_audit_list(
        db, integration=key, limit=limit
    )


@router.post("/integrations/llm/test", response_model=LlmConnectionTestResult)
def test_llm(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> LlmConnectionTestResult:
    del auth, admin
    return admin_integration_service.test_llm_connection(db)


@router.post("/integrations/web-search/test", response_model=WebSearchConnectionTestResult)
def test_web_search(
    body: WebSearchConnectionTestRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> WebSearchConnectionTestResult:
    del auth, admin
    return admin_integration_service.test_web_search_connection(db, body.query)


@router.post("/integrations/embedding/test", response_model=EmbeddingConnectionTestResult)
def test_embedding(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    admin: Annotated[User, Depends(require_system_admin)],
) -> EmbeddingConnectionTestResult:
    del auth, admin
    return admin_integration_service.test_embedding_connection(db)

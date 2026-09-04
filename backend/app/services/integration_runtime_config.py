"""Runtime Integration Config resolver and update service (Step 17.6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.integration_secrets import (
    decrypt_integration_secret,
    encrypt_integration_secret,
    secret_storage_ready,
)
from app.models.enums import (
    IntegrationApiKeyAction,
    IntegrationConfigAuditAction,
    IntegrationKey,
    IntegrationSecretMode,
)
from app.models.idea import Idea
from app.models.integration_runtime import IntegrationConfigAudit, IntegrationRuntimeConfig
from app.models.user import User
from app.services import embedding_service

logger = logging.getLogger(__name__)

IntegrationName = Literal["llm", "web_search", "embedding"]

LLM_CONFIG_FIELDS: dict[str, str] = {
    # request/json field -> Settings attribute
    "api_url": "llm_api_url",
    "model_name": "llm_model_name",
    "chat_completions_path": "llm_chat_completions_path",
    "timeout_seconds": "llm_timeout_seconds",
    "connect_timeout_seconds": "llm_connect_timeout_seconds",
    "temperature": "llm_temperature",
    "max_tokens": "llm_max_tokens",
    "enable_thinking": "llm_enable_thinking",
}

WEB_SEARCH_CONFIG_FIELDS: dict[str, str] = {
    "provider": "web_search_provider",
    "api_url": "web_search_api_url",
    "timeout_seconds": "web_search_timeout_seconds",
    "connect_timeout_seconds": "web_search_connect_timeout_seconds",
    "max_queries": "web_search_max_queries",
    "max_results_per_query": "web_search_max_results_per_query",
    "max_total_results": "web_search_max_total_results",
}

EMBEDDING_CONFIG_FIELDS: dict[str, str] = {
    "enabled": "embedding_enabled",
    "provider": "embedding_provider",
    "api_url": "embedding_api_url",
    "model_name": "embedding_model_name",
    "embedding_path": "embedding_path",
    "timeout_seconds": "embedding_timeout_seconds",
    "connect_timeout_seconds": "embedding_connect_timeout_seconds",
    "max_input_chars": "embedding_max_input_chars",
}

_FIELD_MAPS: dict[IntegrationKey, dict[str, str]] = {
    IntegrationKey.LLM: LLM_CONFIG_FIELDS,
    IntegrationKey.WEB_SEARCH: WEB_SEARCH_CONFIG_FIELDS,
    IntegrationKey.EMBEDDING: EMBEDDING_CONFIG_FIELDS,
}

_SECRET_ATTR: dict[IntegrationKey, str] = {
    IntegrationKey.LLM: "llm_api_key",
    IntegrationKey.WEB_SEARCH: "web_search_api_key",
    IntegrationKey.EMBEDDING: "embedding_api_key",
}

_SUPPORTED_WEB_PROVIDERS = {"http_json", "tavily"}
_SUPPORTED_EMBEDDING_PROVIDERS = {"openai_compatible", "fake"}

# Stable pg_advisory_xact_lock ids (NOT Python hash()).
_ADVISORY_LOCK_IDS: dict[IntegrationKey, int] = {
    IntegrationKey.LLM: 1_760_001,
    IntegrationKey.WEB_SEARCH: 1_760_002,
    IntegrationKey.EMBEDDING: 1_760_003,
}


@dataclass(frozen=True)
class RuntimeMeta:
    configuration_source: str  # RUNTIME | ENVIRONMENT
    runtime_override_exists: bool
    runtime_revision: int
    updated_at: Any | None
    updated_by_id: UUID | None
    updated_by_name: str | None
    secret_mode: str
    api_key_source: str  # RUNTIME | ENVIRONMENT | NONE
    api_key_configured: bool
    secret_storage_ready: bool
    runtime_error_code: str | None = None
    runtime_safe_message: str | None = None


def get_runtime_row(
    db: Session, key: IntegrationKey, *, for_update: bool = False
) -> IntegrationRuntimeConfig | None:
    stmt = select(IntegrationRuntimeConfig).where(
        IntegrationRuntimeConfig.integration_key == key.value
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def get_runtime_revision(db: Session, key: IntegrationKey) -> int:
    row = get_runtime_row(db, key)
    return int(row.revision) if row is not None else 0


def _acquire_integration_lock(db: Session, key: IntegrationKey) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": _ADVISORY_LOCK_IDS[key]},
    )


def _validate_http_url(url: str, *, field: str) -> str:
    stripped = (url or "").strip()
    if not stripped:
        return ""
    parsed = urlparse(stripped)
    if parsed.scheme not in ("http", "https"):
        raise AppError(
            f"{field}는 http 또는 https URL이어야 합니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )
    if parsed.username or parsed.password:
        raise AppError(
            f"{field}에 사용자 인증 정보를 포함할 수 없습니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )
    if parsed.fragment:
        raise AppError(
            f"{field}에 fragment를 포함할 수 없습니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )
    if parsed.query:
        raise AppError(
            f"{field}에 query string을 포함할 수 없습니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )
    if not parsed.netloc:
        raise AppError(
            f"{field}가 올바른 URL이 아닙니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )
    return stripped


def _whitelist_config(key: IntegrationKey, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Whitelist runtime config_json fields; preserve explicit null for enable_thinking."""
    allowed = _FIELD_MAPS[key]
    out: dict[str, Any] = {}
    if not raw:
        return out
    for field in allowed:
        if field not in raw:
            continue
        if field == "enable_thinking":
            out[field] = raw[field]  # may be None
        elif raw[field] is not None:
            out[field] = raw[field]
    return out


def _overlay_config_into_payload(
    payload: dict[str, Any],
    key: IntegrationKey,
    config_json: dict[str, Any],
) -> None:
    """Apply whitelisted config fields onto a Settings.model_dump() payload in-place."""
    field_map = _FIELD_MAPS[key]
    for json_key, attr in field_map.items():
        if json_key not in config_json:
            continue
        if json_key == "enable_thinking":
            payload[attr] = config_json[json_key]  # may be None
        elif config_json[json_key] is not None:
            payload[attr] = config_json[json_key]


def _overlay_secret_into_payload(
    payload: dict[str, Any],
    key: IntegrationKey,
    secret_mode: str,
    ciphertext: str | None,
    base: Settings,
) -> None:
    """Apply secret mode onto payload; decrypt ENCRYPTED ciphertext when needed."""
    secret_attr = _SECRET_ATTR[key]
    if secret_mode == IntegrationSecretMode.CLEARED.value:
        payload[secret_attr] = ""
    elif secret_mode == IntegrationSecretMode.ENCRYPTED.value:
        payload[secret_attr] = decrypt_integration_secret(ciphertext or "", base)
    # INHERIT_ENV: keep ENV secret already present in payload from base


def _validate_settings_payload(payload: dict[str, Any]) -> Settings:
    try:
        return Settings.model_validate(payload)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "Runtime 설정이 유효하지 않습니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        ) from exc


def _current_non_secret_overlay(db: Session, key: IntegrationKey) -> dict[str, Any]:
    row = get_runtime_row(db, key)
    if row is None:
        return {}
    raw = row.config_json if isinstance(row.config_json, dict) else {}
    return _whitelist_config(key, raw)


def resolve_settings_for_integrations(
    db: Session,
    *,
    integrations: Iterable[IntegrationKey],
    base_settings: Settings | None = None,
) -> Settings:
    """Merge selected Runtime overrides onto ENV Settings (single validation)."""
    base = base_settings or get_settings()
    payload = base.model_dump()
    for key in integrations:
        row = get_runtime_row(db, key)
        if row is None:
            continue
        config = _whitelist_config(
            key, row.config_json if isinstance(row.config_json, dict) else {}
        )
        _overlay_config_into_payload(payload, key, config)
        _overlay_secret_into_payload(
            payload,
            key,
            row.secret_mode,
            row.secret_ciphertext,
            base,
        )
    return _validate_settings_payload(payload)


def resolve_settings_non_secret_only(
    db: Session,
    *,
    key: IntegrationKey,
    base_settings: Settings | None = None,
) -> Settings:
    """Overlay runtime config_json only (no secret decrypt) for degraded admin views."""
    base = base_settings or get_settings()
    payload = base.model_dump()
    config = _current_non_secret_overlay(db, key)
    _overlay_config_into_payload(payload, key, config)
    row = get_runtime_row(db, key)
    if row is not None and row.secret_mode == IntegrationSecretMode.CLEARED.value:
        payload[_SECRET_ATTR[key]] = ""
    try:
        return _validate_settings_payload(payload)
    except AppError:
        # Display-only fallback when partial overlay fails global invariants (e.g. lease).
        return Settings.model_construct(**payload)


def _overlay_own_runtime_full(
    db: Session,
    payload: dict[str, Any],
    *,
    key: IntegrationKey,
    base: Settings,
) -> None:
    """Overlay one integration's runtime config_json + secret onto payload."""
    row = get_runtime_row(db, key)
    if row is None:
        return
    config = _whitelist_config(
        key, row.config_json if isinstance(row.config_json, dict) else {}
    )
    _overlay_config_into_payload(payload, key, config)
    _overlay_secret_into_payload(
        payload,
        key,
        row.secret_mode,
        row.secret_ciphertext,
        base,
    )


def resolve_llm_settings(db: Session, base_settings: Settings | None = None) -> Settings:
    """Effective LLM settings with Web Search NON-SECRET runtime for invariants.

    Does not decrypt Web Search secrets. Validates Settings exactly once.
    """
    base = base_settings or get_settings()
    payload = base.model_dump()
    _overlay_config_into_payload(
        payload,
        IntegrationKey.WEB_SEARCH,
        _current_non_secret_overlay(db, IntegrationKey.WEB_SEARCH),
    )
    _overlay_own_runtime_full(db, payload, key=IntegrationKey.LLM, base=base)
    return _validate_settings_payload(payload)


def resolve_web_search_settings(db: Session, base_settings: Settings | None = None) -> Settings:
    """Effective Web Search settings with LLM NON-SECRET runtime for invariants.

    Does not decrypt LLM secrets. Validates Settings exactly once.
    """
    base = base_settings or get_settings()
    payload = base.model_dump()
    _overlay_config_into_payload(
        payload,
        IntegrationKey.LLM,
        _current_non_secret_overlay(db, IntegrationKey.LLM),
    )
    _overlay_own_runtime_full(db, payload, key=IntegrationKey.WEB_SEARCH, base=base)
    return _validate_settings_payload(payload)


def resolve_embedding_settings(db: Session, base_settings: Settings | None = None) -> Settings:
    return resolve_settings_for_integrations(
        db, integrations=[IntegrationKey.EMBEDDING], base_settings=base_settings
    )


def resolve_llm_and_web_search_settings(
    db: Session, base_settings: Settings | None = None
) -> Settings:
    """Full LLM + Web Search effective config (both secrets applied)."""
    return resolve_settings_for_integrations(
        db,
        integrations=[IntegrationKey.LLM, IntegrationKey.WEB_SEARCH],
        base_settings=base_settings,
    )


def _validate_reset_candidate(
    db: Session,
    *,
    key: IntegrationKey,
    base: Settings,
) -> None:
    """Ensure deleting this runtime row leaves a valid ENV+counterpart combination.

    Counterpart secrets are never decrypted. The row being reset is not overlaid
    (ENV fallback for that integration), so broken ciphertext need not be read.
    """
    if key not in (IntegrationKey.LLM, IntegrationKey.WEB_SEARCH):
        return
    payload = base.model_dump()
    if key == IntegrationKey.LLM:
        _overlay_config_into_payload(
            payload,
            IntegrationKey.WEB_SEARCH,
            _current_non_secret_overlay(db, IntegrationKey.WEB_SEARCH),
        )
    else:
        _overlay_config_into_payload(
            payload,
            IntegrationKey.LLM,
            _current_non_secret_overlay(db, IntegrationKey.LLM),
        )
    _validate_settings_payload(payload)


def _api_key_source(
    *,
    secret_mode: str,
    env_key: str,
) -> tuple[str, bool]:
    if secret_mode == IntegrationSecretMode.ENCRYPTED.value:
        # Key is stored even if currently unreadable.
        return "RUNTIME", True
    if secret_mode == IntegrationSecretMode.CLEARED.value:
        return "NONE", False
    # INHERIT_ENV or no runtime row
    if env_key.strip():
        return "ENVIRONMENT", True
    return "NONE", False


def build_runtime_meta(
    db: Session,
    key: IntegrationKey,
    *,
    base: Settings,
    effective: Settings | None = None,
    runtime_error_code: str | None = None,
    runtime_safe_message: str | None = None,
    secret_unreadable: bool = False,
) -> RuntimeMeta:
    row = get_runtime_row(db, key)
    storage_ready = secret_storage_ready(base)
    env_secret = getattr(base, _SECRET_ATTR[key], "") or ""
    if row is None:
        source, configured = _api_key_source(
            secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
            env_key=env_secret,
        )
        return RuntimeMeta(
            configuration_source="ENVIRONMENT",
            runtime_override_exists=False,
            runtime_revision=0,
            updated_at=None,
            updated_by_id=None,
            updated_by_name=None,
            secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
            api_key_source=source,
            api_key_configured=configured,
            secret_storage_ready=storage_ready,
            runtime_error_code=runtime_error_code,
            runtime_safe_message=runtime_safe_message,
        )

    actor_name = None
    if row.updated_by is not None:
        actor = db.get(User, row.updated_by)
        actor_name = actor.name if actor is not None else None
    source, configured = _api_key_source(
        secret_mode=row.secret_mode,
        env_key=env_secret,
    )
    if row.secret_mode == IntegrationSecretMode.ENCRYPTED.value:
        source = "RUNTIME"
        if secret_unreadable or effective is None:
            configured = True
        else:
            eff_secret = getattr(effective, _SECRET_ATTR[key], "") or ""
            configured = bool(eff_secret.strip())
    return RuntimeMeta(
        configuration_source="RUNTIME",
        runtime_override_exists=True,
        runtime_revision=int(row.revision),
        updated_at=row.updated_at,
        updated_by_id=row.updated_by,
        updated_by_name=actor_name,
        secret_mode=row.secret_mode,
        api_key_source=source,
        api_key_configured=configured,
        secret_storage_ready=storage_ready,
        runtime_error_code=runtime_error_code,
        runtime_safe_message=runtime_safe_message,
    )


def build_runtime_meta_from_row_safe(
    db: Session,
    key: IntegrationKey,
    *,
    base: Settings,
    error: AppError,
) -> tuple[Settings, RuntimeMeta]:
    """Build degraded effective Settings + meta without decrypting secrets."""
    degraded = resolve_settings_non_secret_only(db, key=key, base_settings=base)
    meta = build_runtime_meta(
        db,
        key,
        base=base,
        effective=None,
        runtime_error_code=error.code,
        runtime_safe_message=error.message,
        secret_unreadable=True,
    )
    return degraded, meta


def _write_audit(
    db: Session,
    *,
    key: IntegrationKey,
    action: str,
    changed_fields: list[str],
    revision: int,
    actor_id: UUID | None,
) -> None:
    db.add(
        IntegrationConfigAudit(
            id=uuid4(),
            integration_key=key.value,
            action=action,
            changed_fields=changed_fields,
            revision=revision,
            actor_id=actor_id,
        )
    )


def _reject_production_fake_embedding(provider: str, base: Settings) -> None:
    if provider == "fake" and (base.app_env or "").strip().lower() == "production":
        raise AppError(
            "production 환경에서는 fake 임베딩 Provider를 사용할 수 없습니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )


def _normalize_patch_config(
    key: IntegrationKey, data: dict[str, Any], *, base: Settings
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, value in data.items():
        if field not in _FIELD_MAPS[key]:
            continue
        if field in ("api_url",) or field.endswith("_url"):
            out[field] = _validate_http_url(str(value) if value is not None else "", field=field)
        elif field == "provider":
            provider = str(value).strip().lower()
            if key == IntegrationKey.WEB_SEARCH and provider not in _SUPPORTED_WEB_PROVIDERS:
                raise AppError(
                    "지원하지 않는 웹 검색 Provider입니다.",
                    code="INTEGRATION_RUNTIME_CONFIG_INVALID",
                    status_code=400,
                )
            if key == IntegrationKey.EMBEDDING and provider not in _SUPPORTED_EMBEDDING_PROVIDERS:
                raise AppError(
                    "지원하지 않는 임베딩 Provider입니다.",
                    code="INTEGRATION_RUNTIME_CONFIG_INVALID",
                    status_code=400,
                )
            if key == IntegrationKey.EMBEDDING:
                _reject_production_fake_embedding(provider, base)
            if key == IntegrationKey.LLM and provider != "openai_compatible":
                raise AppError(
                    "LLM Provider는 openai_compatible만 지원합니다.",
                    code="INTEGRATION_RUNTIME_CONFIG_INVALID",
                    status_code=400,
                )
            out[field] = provider
        elif isinstance(value, str) and field in ("model_name", "chat_completions_path", "embedding_path"):
            stripped = value.strip()
            if not stripped and field == "model_name":
                raise AppError(
                    "model_name은 비워둘 수 없습니다.",
                    code="INTEGRATION_RUNTIME_CONFIG_INVALID",
                    status_code=400,
                )
            out[field] = stripped
        elif field == "enable_thinking":
            out[field] = value  # may be None (explicit clear)
        else:
            out[field] = value
    return out


def _identity_changed(
    before: dict[str, Any], after: dict[str, Any], *, fields: tuple[str, ...]
) -> bool:
    for f in fields:
        if before.get(f) != after.get(f):
            return True
    return False


def _schedule_embedding_reindex(db: Session, settings: Settings) -> None:
    """Delete stored vectors and enqueue jobs for all active ideas (force)."""
    ideas = db.execute(select(Idea).where(Idea.deleted_at.is_(None))).scalars().all()
    for idea in ideas:
        embedding_service.sync_embedding_desired_state(
            db, idea, settings=settings, force=True
        )


def _schedule_embedding_backfill(db: Session, settings: Settings) -> None:
    """Enqueue missing/stale embeddings without force (disabled→enabled)."""
    embedding_service.scan_ideas_for_enqueue(db, force=False, settings=settings)


def _embedding_identity_from_settings(settings: Settings) -> dict[str, Any]:
    return {
        "provider": settings.embedding_provider,
        "model_name": settings.embedding_model_name,
        "enabled": bool(settings.embedding_enabled),
    }


def _embedding_identity_from_overlay(
    base: Settings, config: dict[str, Any]
) -> dict[str, Any]:
    return {
        "provider": config.get("provider", base.embedding_provider),
        "model_name": config.get("model_name", base.embedding_model_name),
        "enabled": (
            bool(config["enabled"])
            if "enabled" in config
            else bool(base.embedding_enabled)
        ),
    }


def _resolve_before_embedding_state(
    db: Session, *, base: Settings, previous_config: dict[str, Any]
) -> dict[str, Any]:
    try:
        before = resolve_embedding_settings(db, base_settings=base)
        return _embedding_identity_from_settings(before)
    except AppError:
        return _embedding_identity_from_overlay(base, previous_config)


def _validate_upsert_candidate(
    db: Session,
    *,
    key: IntegrationKey,
    base: Settings,
    merged: dict[str, Any],
    next_mode: str,
    next_cipher: str | None,
) -> Settings:
    """One-shot Settings validation with cross-integration non-secret overlays."""
    payload = base.model_dump()

    if key == IntegrationKey.LLM:
        _overlay_config_into_payload(
            payload,
            IntegrationKey.WEB_SEARCH,
            _current_non_secret_overlay(db, IntegrationKey.WEB_SEARCH),
        )
    elif key == IntegrationKey.WEB_SEARCH:
        _overlay_config_into_payload(
            payload,
            IntegrationKey.LLM,
            _current_non_secret_overlay(db, IntegrationKey.LLM),
        )

    _overlay_config_into_payload(payload, key, merged)
    _overlay_secret_into_payload(payload, key, next_mode, next_cipher, base)
    return _validate_settings_payload(payload)


def upsert_runtime_config(
    db: Session,
    *,
    key: IntegrationKey,
    actor_id: UUID,
    expected_revision: int,
    patch_fields: dict[str, Any],
    api_key_action: str,
    api_key: str | None,
    base_settings: Settings | None = None,
) -> IntegrationRuntimeConfig:
    base = base_settings or get_settings()
    _acquire_integration_lock(db, key)
    row = get_runtime_row(db, key, for_update=True)
    current_revision = int(row.revision) if row is not None else 0
    if expected_revision != current_revision:
        raise AppError(
            "다른 관리자가 설정을 변경했습니다. 최신 설정을 다시 불러온 후 시도해 주세요.",
            code="INTEGRATION_CONFIG_CHANGED",
            status_code=409,
        )

    previous_config = (
        _whitelist_config(key, row.config_json if row and isinstance(row.config_json, dict) else {})
        if row
        else {}
    )
    merged = dict(previous_config)
    normalized = _normalize_patch_config(key, patch_fields, base=base)
    # Explicit null for enable_thinking must remain in JSONB after update.
    merged.update(normalized)

    # Reject production fake even when inherited from previous merged config
    if key == IntegrationKey.EMBEDDING:
        provider = str(merged.get("provider", base.embedding_provider)).strip().lower()
        _reject_production_fake_embedding(provider, base)

    # Secret handling
    prev_mode = row.secret_mode if row is not None else IntegrationSecretMode.INHERIT_ENV.value
    prev_cipher = row.secret_ciphertext if row is not None else None
    next_mode = prev_mode
    next_cipher = prev_cipher
    secret_action_audit: str | None = None

    action = (api_key_action or IntegrationApiKeyAction.KEEP.value).upper()
    if action == IntegrationApiKeyAction.KEEP.value:
        pass
    elif action == IntegrationApiKeyAction.REPLACE.value:
        if not secret_storage_ready(base):
            raise AppError(
                "새 API Key를 Runtime에 저장하려면 서버의 INTEGRATION_SECRET_ENCRYPTION_KEY 설정이 필요합니다.",
                code="INTEGRATION_SECRET_ENCRYPTION_NOT_CONFIGURED",
                status_code=400,
            )
        next_cipher = encrypt_integration_secret(api_key or "", base)
        next_mode = IntegrationSecretMode.ENCRYPTED.value
        secret_action_audit = IntegrationConfigAuditAction.SECRET_REPLACED.value
    elif action == IntegrationApiKeyAction.CLEAR.value:
        next_cipher = None
        next_mode = IntegrationSecretMode.CLEARED.value
        secret_action_audit = IntegrationConfigAuditAction.SECRET_CLEARED.value
    elif action == IntegrationApiKeyAction.INHERIT_ENV.value:
        next_cipher = None
        next_mode = IntegrationSecretMode.INHERIT_ENV.value
        secret_action_audit = IntegrationConfigAuditAction.SECRET_INHERIT_ENV.value
    else:
        raise AppError(
            "알 수 없는 api_key_action입니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )

    # Validate merged effective settings before write (one-shot, with cross overlays)
    candidate = _validate_upsert_candidate(
        db,
        key=key,
        base=base,
        merged=merged,
        next_mode=next_mode,
        next_cipher=next_cipher,
    )

    # Embedding identity / enabled transition detection
    schedule_reindex = False
    schedule_backfill = False
    before_state: dict[str, Any] | None = None
    if key == IntegrationKey.EMBEDDING:
        before_state = _resolve_before_embedding_state(
            db, base=base, previous_config=previous_config if row else {}
        )
        after_state = _embedding_identity_from_settings(candidate)
        if _identity_changed(
            before_state, after_state, fields=("provider", "model_name")
        ):
            schedule_reindex = True
        elif (not before_state["enabled"]) and after_state["enabled"]:
            schedule_backfill = True

    changed_fields = sorted(
        {f for f in normalized.keys()}
        | ({"api_key"} if secret_action_audit else set())
    )

    created = row is None
    if row is None:
        row = IntegrationRuntimeConfig(
            integration_key=key.value,
            config_json=merged,
            secret_mode=next_mode,
            secret_ciphertext=next_cipher,
            revision=1,
            updated_by=actor_id,
        )
        db.add(row)
        new_revision = 1
        primary_action = IntegrationConfigAuditAction.CREATED.value
    else:
        row.config_json = merged
        row.secret_mode = next_mode
        row.secret_ciphertext = next_cipher
        row.revision = int(row.revision) + 1
        row.updated_by = actor_id
        new_revision = int(row.revision)
        primary_action = IntegrationConfigAuditAction.UPDATED.value

    db.flush()

    if secret_action_audit:
        _write_audit(
            db,
            key=key,
            action=secret_action_audit,
            changed_fields=["api_key"],
            revision=new_revision,
            actor_id=actor_id,
        )

    non_secret_changed = [f for f in changed_fields if f != "api_key"]
    if created or non_secret_changed:
        _write_audit(
            db,
            key=key,
            action=primary_action,
            changed_fields=non_secret_changed or changed_fields,
            revision=new_revision,
            actor_id=actor_id,
        )

    if schedule_reindex:
        _schedule_embedding_reindex(db, candidate)
    elif schedule_backfill:
        _schedule_embedding_backfill(db, candidate)

    logger.info(
        "integration_runtime_config_saved key=%s revision=%s actor=%s fields=%s",
        key.value,
        new_revision,
        actor_id,
        changed_fields,
    )
    return row


def reset_runtime_config(
    db: Session,
    *,
    key: IntegrationKey,
    actor_id: UUID,
    expected_revision: int,
    base_settings: Settings | None = None,
) -> None:
    base = base_settings or get_settings()
    _acquire_integration_lock(db, key)
    row = get_runtime_row(db, key, for_update=True)
    current_revision = int(row.revision) if row is not None else 0
    if expected_revision != current_revision:
        raise AppError(
            "다른 관리자가 설정을 변경했습니다. 최신 설정을 다시 불러온 후 시도해 주세요.",
            code="INTEGRATION_CONFIG_CHANGED",
            status_code=409,
        )
    if row is None:
        return

    # LLM/Web reset must leave a valid ENV + counterpart non-secret combination.
    # Do not decrypt the row being deleted (or counterpart secrets).
    _validate_reset_candidate(db, key=key, base=base)

    before_state: dict[str, Any] | None = None
    if key == IntegrationKey.EMBEDDING:
        previous_config = _whitelist_config(
            key, row.config_json if isinstance(row.config_json, dict) else {}
        )
        before_state = _resolve_before_embedding_state(
            db, base=base, previous_config=previous_config
        )

    rev = int(row.revision)
    db.delete(row)
    db.flush()

    if key == IntegrationKey.EMBEDDING and before_state is not None:
        after_state = _embedding_identity_from_settings(base)
        if _identity_changed(
            before_state, after_state, fields=("provider", "model_name")
        ):
            _schedule_embedding_reindex(db, base)
        elif (not before_state["enabled"]) and after_state["enabled"]:
            _schedule_embedding_backfill(db, base)

    _write_audit(
        db,
        key=key,
        action=IntegrationConfigAuditAction.RESET_TO_ENV.value,
        changed_fields=[],
        revision=rev,
        actor_id=actor_id,
    )
    logger.info(
        "integration_runtime_config_reset key=%s revision=%s actor=%s",
        key.value,
        rev,
        actor_id,
    )


def list_config_audits(
    db: Session,
    *,
    integration: IntegrationKey | None = None,
    limit: int = 20,
) -> list[IntegrationConfigAudit]:
    stmt = select(IntegrationConfigAudit).order_by(IntegrationConfigAudit.created_at.desc())
    if integration is not None:
        stmt = stmt.where(IntegrationConfigAudit.integration_key == integration.value)
    stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())

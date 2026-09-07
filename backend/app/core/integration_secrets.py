"""Fernet helpers for Runtime Integration API Key secrets (Step 17.6)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, get_settings
from app.core.errors import AppError


class IntegrationSecretError(AppError):
    """Safe secret encryption/decryption failures."""


def secret_storage_ready(settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    key = (cfg.integration_secret_encryption_key or "").strip()
    if not key:
        return False
    try:
        Fernet(key.encode("utf-8") if isinstance(key, str) else key)
        return True
    except Exception:
        return False


def _fernet(settings: Settings) -> Fernet:
    raw = (settings.integration_secret_encryption_key or "").strip()
    if not raw:
        raise IntegrationSecretError(
            "Runtime API Key를 저장하려면 서버 암호화 키 설정이 필요합니다.",
            code="INTEGRATION_SECRET_ENCRYPTION_NOT_CONFIGURED",
            status_code=400,
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except Exception as exc:
        raise IntegrationSecretError(
            "서버 암호화 키 설정을 확인할 수 없습니다.",
            code="INTEGRATION_SECRET_ENCRYPTION_NOT_CONFIGURED",
            status_code=400,
        ) from exc


def encrypt_integration_secret(value: str, settings: Settings | None = None) -> str:
    plaintext = (value or "").strip()
    if not plaintext:
        raise IntegrationSecretError(
            "API Key가 비어 있습니다.",
            code="INTEGRATION_RUNTIME_CONFIG_INVALID",
            status_code=400,
        )
    cfg = settings or get_settings()
    token = _fernet(cfg).encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_integration_secret(ciphertext: str, settings: Settings | None = None) -> str:
    if not ciphertext or not ciphertext.strip():
        raise IntegrationSecretError(
            "저장된 Runtime API Key를 읽을 수 없습니다.",
            code="INTEGRATION_SECRET_DECRYPTION_FAILED",
            status_code=500,
        )
    cfg = settings or get_settings()
    try:
        plain = _fernet(cfg).decrypt(ciphertext.strip().encode("utf-8"))
        return plain.decode("utf-8")
    except IntegrationSecretError:
        raise
    except InvalidToken as exc:
        raise IntegrationSecretError(
            "Runtime API Key가 저장되어 있으나 서버 암호화 키 설정을 확인할 수 없습니다.",
            code="INTEGRATION_SECRET_DECRYPTION_FAILED",
            status_code=500,
        ) from exc
    except Exception as exc:
        raise IntegrationSecretError(
            "Runtime API Key가 저장되어 있으나 서버 암호화 키 설정을 확인할 수 없습니다.",
            code="INTEGRATION_SECRET_DECRYPTION_FAILED",
            status_code=500,
        ) from exc

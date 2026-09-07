"""Unit tests for Runtime Integration secret encryption (Step 17.6)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.integration_secrets import (
    IntegrationSecretError,
    decrypt_integration_secret,
    encrypt_integration_secret,
    secret_storage_ready,
)


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="",
        ai_worker_enabled=False,
        embedding_worker_enabled=False,
        integration_secret_encryption_key="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_encrypt_decrypt_roundtrip() -> None:
    key = Fernet.generate_key().decode("utf-8")
    settings = _settings(integration_secret_encryption_key=key)
    plaintext = "runtime-api-key-value-xyz"
    ciphertext = encrypt_integration_secret(plaintext, settings)
    assert ciphertext != plaintext
    assert decrypt_integration_secret(ciphertext, settings) == plaintext
    assert secret_storage_ready(settings) is True


def test_missing_master_key_raises() -> None:
    settings = _settings(integration_secret_encryption_key="")
    assert secret_storage_ready(settings) is False
    with pytest.raises(IntegrationSecretError) as exc:
        encrypt_integration_secret("some-key", settings)
    assert exc.value.code == "INTEGRATION_SECRET_ENCRYPTION_NOT_CONFIGURED"
    assert exc.value.status_code == 400


def test_invalid_master_key_raises_safe_error() -> None:
    settings = _settings(integration_secret_encryption_key="not-a-valid-fernet-key!!")
    assert secret_storage_ready(settings) is False
    with pytest.raises(IntegrationSecretError) as exc:
        encrypt_integration_secret("some-key", settings)
    assert exc.value.code == "INTEGRATION_SECRET_ENCRYPTION_NOT_CONFIGURED"
    assert "fernet" not in str(exc.value).lower()
    assert "traceback" not in str(exc.value).lower()


def test_invalid_ciphertext_raises_decryption_failed() -> None:
    key = Fernet.generate_key().decode("utf-8")
    settings = _settings(integration_secret_encryption_key=key)
    with pytest.raises(IntegrationSecretError) as exc:
        decrypt_integration_secret("gAAAAABnot-valid-ciphertext-payload", settings)
    assert exc.value.code == "INTEGRATION_SECRET_DECRYPTION_FAILED"
    assert exc.value.status_code == 500


def test_wrong_master_key_cannot_decrypt() -> None:
    key_a = Fernet.generate_key().decode("utf-8")
    key_b = Fernet.generate_key().decode("utf-8")
    settings_a = _settings(integration_secret_encryption_key=key_a)
    settings_b = _settings(integration_secret_encryption_key=key_b)
    ciphertext = encrypt_integration_secret("secret-value", settings_a)
    with pytest.raises(IntegrationSecretError) as exc:
        decrypt_integration_secret(ciphertext, settings_b)
    assert exc.value.code == "INTEGRATION_SECRET_DECRYPTION_FAILED"


def test_empty_plaintext_encrypt_rejected() -> None:
    key = Fernet.generate_key().decode("utf-8")
    settings = _settings(integration_secret_encryption_key=key)
    for blank in ("", "   ", "\t"):
        with pytest.raises(IntegrationSecretError) as exc:
            encrypt_integration_secret(blank, settings)
        assert exc.value.code == "INTEGRATION_RUNTIME_CONFIG_INVALID"
        assert exc.value.status_code == 400


def test_empty_ciphertext_decrypt_rejected() -> None:
    key = Fernet.generate_key().decode("utf-8")
    settings = _settings(integration_secret_encryption_key=key)
    with pytest.raises(IntegrationSecretError) as exc:
        decrypt_integration_secret("", settings)
    assert exc.value.code == "INTEGRATION_SECRET_DECRYPTION_FAILED"

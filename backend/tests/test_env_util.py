"""Tests for deployment env_util helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ENV_UTIL_PATH = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "env_util.py"
_spec = importlib.util.spec_from_file_location("env_util", _ENV_UTIL_PATH)
assert _spec and _spec.loader
env_util = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(env_util)


def test_url_encode_password_handles_reserved_characters() -> None:
    encoded = env_util.url_encode_password("p@ss:word")
    assert encoded == "p%40ss%3Aword"


def test_build_database_url_uses_encoded_password(tmp_path) -> None:
    url = env_util.build_database_url("ideaflow", "p@ss:word", "ideaflow")
    assert url == "postgresql+psycopg://ideaflow:p%40ss%3Aword@db:5432/ideaflow"


def test_set_and_get_value_roundtrip(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\n# comment\n", encoding="utf-8")
    env_util.set_value(str(env_path), "POSTGRES_PASSWORD", "p@ss:word")
    env_util.set_value(str(env_path), "BAZ", "qux")
    assert env_util.get_value(str(env_path), "POSTGRES_PASSWORD") == "p@ss:word"
    assert env_util.get_value(str(env_path), "BAZ") == "qux"
    assert env_util.get_value(str(env_path), "FOO") == "bar"

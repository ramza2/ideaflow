"""Tests for deployment env_util helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ENV_UTIL_PATH = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "env_util.py"
_spec = importlib.util.spec_from_file_location("env_util", _ENV_UTIL_PATH)
assert _spec and _spec.loader
env_util = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(env_util)


@pytest.mark.parametrize(
    ("value", "expected_formatted"),
    [
        ("abc$123 xyz", "'abc$123 xyz'"),
        ("${HOME}-password", "'${HOME}-password'"),
        ("quote'value", "'quote\\'value'"),
    ],
)
def test_format_dotenv_value_explicit_compose_quoting(value: str, expected_formatted: str) -> None:
    assert env_util._format_dotenv_value(value) == expected_formatted


@pytest.mark.parametrize(
    ("password", "expected_encoded"),
    [
        ("simple-password", "simple-password"),
        ("p@ss:word", "p%40ss%3Aword"),
        ("abc$123 xyz", "abc%24123%20xyz"),
        ("${HOME}-password", "%24%7BHOME%7D-password"),
        ("space password", "space%20password"),
        ("quote'value", "quote%27value"),
    ],
)
def test_url_encode_password_cases(password: str, expected_encoded: str) -> None:
    assert env_util.url_encode_password(password) == expected_encoded


@pytest.mark.parametrize(
    ("password", "expected_url_suffix"),
    [
        ("simple-password", "simple-password@db:5432/ideaflow"),
        ("p@ss:word", "p%40ss%3Aword@db:5432/ideaflow"),
        ("abc$123 xyz", "abc%24123%20xyz@db:5432/ideaflow"),
        ("${HOME}-password", "%24%7BHOME%7D-password@db:5432/ideaflow"),
    ],
)
def test_build_database_url_percent_encoding(password: str, expected_url_suffix: str) -> None:
    url = env_util.build_database_url("ideaflow", password, "ideaflow")
    assert url == f"postgresql+psycopg://ideaflow:{expected_url_suffix}"


@pytest.mark.parametrize(
    "password",
    [
        "simple-password",
        "p@ss:word",
        "abc$123 xyz",
        "${HOME}-password",
        "space password",
        "quote'value",
    ],
)
def test_dotenv_roundtrip_preserves_literal_password(tmp_path, password: str) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\n", encoding="utf-8")
    env_util.set_value(str(env_path), "POSTGRES_PASSWORD", password)
    assert env_util.get_value(str(env_path), "POSTGRES_PASSWORD") == password


def test_dotenv_dollar_literal_uses_single_quotes(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    env_util.set_value(str(env_path), "POSTGRES_PASSWORD", "abc$123 xyz")
    line = next(
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("POSTGRES_PASSWORD=")
    )
    assert line == "POSTGRES_PASSWORD='abc$123 xyz'"
    assert env_util.get_value(str(env_path), "POSTGRES_PASSWORD") == "abc$123 xyz"


def test_dotenv_dollar_brace_literal_uses_single_quotes(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    env_util.set_value(str(env_path), "POSTGRES_PASSWORD", "${HOME}-password")
    line = next(
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("POSTGRES_PASSWORD=")
    )
    assert line == "POSTGRES_PASSWORD='${HOME}-password'"


def test_dotenv_single_quote_escape_uses_compose_syntax(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    env_util.set_value(str(env_path), "POSTGRES_PASSWORD", "quote'value")
    line = next(
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("POSTGRES_PASSWORD=")
    )
    assert line == "POSTGRES_PASSWORD='quote\\'value'"
    assert env_util.get_value(str(env_path), "POSTGRES_PASSWORD") == "quote'value"


def test_dotenv_rejects_control_characters() -> None:
    with pytest.raises(ValueError, match="unsupported control characters"):
        env_util._format_dotenv_value("bad\npassword")


def test_database_url_stdin_command(capsys, monkeypatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("p@ss:word"))
    monkeypatch.setattr(
        "sys.argv",
        ["env_util.py", "database-url-stdin", "ideaflow", "ideaflow"],
    )
    assert env_util.main() == 0
    assert (
        capsys.readouterr().out.strip()
        == "postgresql+psycopg://ideaflow:p%40ss%3Aword@db:5432/ideaflow"
    )

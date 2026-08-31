#!/usr/bin/env python3
"""Safe .env file helpers (no secret logging)."""

from __future__ import annotations

import re
import sys
from urllib.parse import quote


_UNQUOTED_SAFE = re.compile(r"^[\w./:@+-]+$")
_CONTROL_CHARS = re.compile(r"[\n\r\x00]")


def _validate_dotenv_scalar(value: str) -> None:
    if _CONTROL_CHARS.search(value):
        raise ValueError("Value contains unsupported control characters")


def _format_dotenv_value(value: str) -> str:
    """Format a value for Docker Compose .env literal preservation."""
    _validate_dotenv_scalar(value)
    if _UNQUOTED_SAFE.fullmatch(value):
        return value
    escaped = value.replace("'", "'\\''")
    return f"'{escaped}'"


def _parse_raw_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        quote_char = raw[0]
        inner = raw[1:-1]
        if quote_char == "'":
            return inner.replace("'\\''", "'")
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return raw


def get_value(path: str, key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = pattern.match(stripped)
            if not match:
                continue
            return _parse_raw_value(match.group(1))
    return None


def set_value(path: str, key: str, value: str) -> None:
    rendered = f"{key}={_format_dotenv_value(value)}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$")
    lines: list[str] = []
    found = False
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if pattern.match(line.rstrip("\n")):
                lines.append(rendered + "\n")
                found = True
            else:
                lines.append(line)
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        lines.append(rendered + "\n")
    with open(path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


def url_encode_password(password: str) -> str:
    return quote(password, safe="")


def build_database_url(user: str, password: str, database: str) -> str:
    encoded = url_encode_password(password)
    return f"postgresql+psycopg://{user}:{encoded}@db:5432/{database}"


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    command = sys.argv[1]
    if command == "get" and len(sys.argv) == 4:
        value = get_value(sys.argv[2], sys.argv[3])
        if value is not None:
            print(value)
        return 0
    if command == "set" and len(sys.argv) == 5:
        set_value(sys.argv[2], sys.argv[3], sys.argv[4])
        return 0
    if command == "set-stdin" and len(sys.argv) == 4:
        value = sys.stdin.read().rstrip("\n")
        set_value(sys.argv[2], sys.argv[3], value)
        return 0
    if command == "database-url-stdin" and len(sys.argv) == 4:
        password = sys.stdin.read().rstrip("\n")
        print(build_database_url(sys.argv[2], password, sys.argv[3]))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

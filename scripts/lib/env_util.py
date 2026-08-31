#!/usr/bin/env python3
"""Safe .env file helpers (no secret logging)."""

from __future__ import annotations

import re
import sys
from urllib.parse import quote


def _format_dotenv_value(value: str) -> str:
    if re.fullmatch(r"[\w./:@+-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
            raw = match.group(1).strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
                quote_char = raw[0]
                inner = raw[1:-1]
                if quote_char == '"':
                    inner = inner.replace('\\"', '"').replace("\\\\", "\\")
                return inner
            return raw
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
    if command == "database-url" and len(sys.argv) == 5:
        print(build_database_url(sys.argv[2], sys.argv[3], sys.argv[4]))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

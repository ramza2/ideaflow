"""Unit tests for Research evidence/query compare rules (Step 26).

Mirrors frontend/src/utils/researchCompare.ts — deterministic URL identity.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_evidence_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        path = parts.path.rstrip("/") if parts.path not in ("", "/") else parts.path
        cleaned = urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))
        return cleaned.lower()
    except Exception:  # noqa: BLE001
        return raw.split("#", 1)[0].rstrip("/").lower()


def compare_evidence_by_url(
    left: list[dict[str, str]],
    right: list[dict[str, str]],
) -> dict[str, list[str]]:
    left_map: dict[str, dict[str, str]] = {}
    right_map: dict[str, dict[str, str]] = {}
    for item in left:
        key = normalize_evidence_url(item["url"])
        if key and key not in left_map:
            left_map[key] = item
    for item in right:
        key = normalize_evidence_url(item["url"])
        if key and key not in right_map:
            right_map[key] = item

    added: list[str] = []
    removed: list[str] = []
    unchanged: list[str] = []
    for key in sorted(set(left_map) | set(right_map)):
        if key in left_map and key in right_map:
            unchanged.append(key)
        elif key in right_map:
            added.append(key)
        else:
            removed.append(key)
    return {"added": added, "removed": removed, "unchanged": unchanged}


def test_normalize_strips_fragment_and_trailing_slash() -> None:
    assert normalize_evidence_url("https://Example.com/Path/#section") == (
        "https://example.com/path"
    )
    assert normalize_evidence_url("https://example.com/path/") == "https://example.com/path"


def test_compare_evidence_added_removed_unchanged_deterministic() -> None:
    left = [
        {"title": "A", "url": "https://example.com/a"},
        {"title": "B", "url": "https://example.com/b/"},
        {"title": "C", "url": "https://example.com/c#x"},
    ]
    right = [
        {"title": "B2", "url": "https://example.com/b"},
        {"title": "C2", "url": "https://EXAMPLE.com/c"},
        {"title": "D", "url": "https://example.com/d"},
    ]
    result = compare_evidence_by_url(left, right)
    assert result["added"] == ["https://example.com/d"]
    assert result["removed"] == ["https://example.com/a"]
    assert result["unchanged"] == [
        "https://example.com/b",
        "https://example.com/c",
    ]


def test_compare_ignores_duplicate_urls_keeps_first() -> None:
    left = [
        {"title": "First", "url": "https://example.com/a"},
        {"title": "Dup", "url": "https://example.com/a/"},
    ]
    right = [{"title": "Right", "url": "https://example.com/a"}]
    result = compare_evidence_by_url(left, right)
    assert result["added"] == []
    assert result["removed"] == []
    assert result["unchanged"] == ["https://example.com/a"]

"""Deterministic canonical text for Idea embeddings."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.models.idea import Idea

# Field order for truncation priority (most important first).
_TRUNCATION_FIELD_ORDER: list[tuple[str, str]] = [
    ("title", "Title"),
    ("one_line_definition", "One-line definition"),
    ("problem", "Problem"),
    ("core_concept", "Core concept"),
    ("major_features", "Major features"),
    ("original_text", "Original"),
    ("background", "Background"),
    ("expected_effect", "Expected effect"),
    ("target_users", "Target users"),
    ("scenarios", "Scenarios"),
    ("challenges", "Challenges"),
    ("minimum_validation", "Minimum validation"),
    ("related_project", "Related project"),
]


def _field_value(idea: Idea, attr: str) -> str | None:
    value = getattr(idea, attr, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_idea_embedding_text(
    idea: Idea,
    tag_names: list[str],
    *,
    max_chars: int | None = None,
) -> str:
    """Build deterministic embedding corpus from Idea content fields and tags."""
    sections: list[str] = []

    for attr, label in _TRUNCATION_FIELD_ORDER:
        value = _field_value(idea, attr)
        if value:
            sections.append(f"{label}:\n{value}")

    normalized_tags = sorted({t.strip() for t in tag_names if t and t.strip()})
    if normalized_tags:
        sections.append(f"Tags:\n{', '.join(normalized_tags)}")

    if not sections:
        return ""

    full_text = "\n\n".join(sections)
    cap = max_chars
    if cap is None:
        cap = get_settings().embedding_max_input_chars
    if len(full_text) <= cap:
        return full_text
    return _truncate_sections(sections, cap)


def _truncate_sections(sections: list[str], max_chars: int) -> str:
    """Truncate by dropping lowest-priority sections, then hard-truncate last section."""
    kept: list[str] = []
    total = 0
    for section in sections:
        if total + len(section) + (2 if kept else 0) <= max_chars:
            kept.append(section)
            total += len(section) + (2 if kept else 0)
            continue
        remaining = max_chars - total - (2 if kept else 0)
        if remaining > 0:
            kept.append(section[:remaining])
        break
    return "\n\n".join(kept)


# Fields whose changes require embedding regeneration.
EMBEDDING_CONTENT_FIELDS = frozenset(
    {
        "title",
        "one_line_definition",
        "original_text",
        "background",
        "problem",
        "core_concept",
        "major_features",
        "expected_effect",
        "target_users",
        "scenarios",
        "challenges",
        "minimum_validation",
        "related_project",
        "tags",
    }
)


def embedding_fields_changed(fields_set: set[str]) -> bool:
    return bool(fields_set & EMBEDDING_CONTENT_FIELDS)


def compute_content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_embedding_current(
    *,
    stored_hash: str | None,
    stored_model: str | None,
    stored_dimension: int | None,
    current_hash: str,
    settings: Settings | None = None,
) -> bool:
    cfg = settings or get_settings()
    return (
        stored_hash == current_hash
        and stored_model == cfg.embedding_model_name
        and stored_dimension == cfg.embedding_dimension
    )

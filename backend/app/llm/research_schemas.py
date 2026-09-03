"""LLM evidence refinement schemas (Step 9)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.llm.exceptions import LlmResponseValidationError
from app.llm.schemas import strip_json_fence
from app.models.enums import FieldProvenanceSource

RESEARCH_REFINABLE_FIELDS = (
    "title",
    "one_line_definition",
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
)


class EvidenceInput(BaseModel):
    evidence_id: UUID
    title: str
    source: str | None = None
    published_at: str | None = None
    snippet: str | None = None


class EvidenceRefinementRequest(BaseModel):
    input_text: str
    base_draft: dict[str, Any]
    base_provenance: dict[str, Any] = Field(default_factory=dict)
    user_edited_fields: list[str] = Field(default_factory=list)
    evidence: list[EvidenceInput] = Field(default_factory=list)


class EvidenceRefinementResult(BaseModel):
    draft: dict[str, Any]
    evidence_links: dict[str, list[str]] = Field(default_factory=dict)
    research_summary: str | None = None

    @field_validator("evidence_links", mode="before")
    @classmethod
    def coerce_links(cls, value: Any) -> dict[str, list[str]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("evidence_links must be an object")
        out: dict[str, list[str]] = {}
        for key, ids in value.items():
            if ids is None:
                continue
            if not isinstance(ids, list):
                raise ValueError("evidence_links values must be lists")
            out[str(key)] = [str(x) for x in ids]
        return out


def parse_refinement_result(content: str) -> EvidenceRefinementResult:
    import json

    cleaned = strip_json_fence(content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LlmResponseValidationError("LLM response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise LlmResponseValidationError("LLM response must be a JSON object")
    try:
        return EvidenceRefinementResult.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise LlmResponseValidationError("LLM response failed schema validation") from exc


def filter_user_edited_refinement_fields(
    result: EvidenceRefinementResult,
    user_edited_fields: list[str],
) -> tuple[EvidenceRefinementResult, int]:
    """Strip user-edited fields from LLM refinement output before validation/merge."""
    edited = {field for field in user_edited_fields if field in RESEARCH_REFINABLE_FIELDS}
    if not edited:
        return result, 0

    ignored = 0
    for field in edited:
        if field in result.draft or field in result.evidence_links:
            ignored += 1

    filtered_draft = {
        field: value
        for field, value in result.draft.items()
        if field in RESEARCH_REFINABLE_FIELDS and field not in edited
    }
    filtered_links = {
        field: ids
        for field, ids in result.evidence_links.items()
        if field in RESEARCH_REFINABLE_FIELDS and field not in edited
    }
    return (
        EvidenceRefinementResult(
            draft=filtered_draft,
            evidence_links=filtered_links,
            research_summary=result.research_summary,
        ),
        ignored,
    )


def validate_refinement_result(
    result: EvidenceRefinementResult,
    *,
    base_draft: dict[str, Any],
    user_edited_fields: list[str],
    valid_evidence_ids: set[str],
) -> EvidenceRefinementResult:
    """Validate business rules for evidence-grounded refinement."""
    edited = set(user_edited_fields)
    draft = dict(base_draft)

    for field in RESEARCH_REFINABLE_FIELDS:
        base_val = base_draft.get(field)
        new_val = result.draft.get(field, base_val)
        if field in edited:
            if new_val != base_val:
                raise LlmResponseValidationError(
                    f"LLM changed user-edited field: {field}",
                )
            continue

        if new_val == base_val:
            continue

        links = result.evidence_links.get(field) or []
        if not links:
            raise LlmResponseValidationError(
                f"Changed field {field} lacks evidence_links",
            )
        for eid in links:
            if eid not in valid_evidence_ids:
                raise LlmResponseValidationError(
                    f"Unknown evidence_id in evidence_links: {eid}",
                )

    return result


def merge_refinement_provenance(
    *,
    base_provenance: dict[str, Any] | None,
    base_draft: dict[str, Any],
    refined_draft: dict[str, Any],
    evidence_links: dict[str, list[str]],
    user_edited_fields: list[str],
) -> dict[str, Any]:
    """Merge WEB_EVIDENCE provenance for changed fields only."""
    edited = set(user_edited_fields)
    provenance = dict(base_provenance or {})

    for field in RESEARCH_REFINABLE_FIELDS:
        if field in edited:
            continue
        base_val = base_draft.get(field)
        new_val = refined_draft.get(field, base_val)
        if new_val == base_val:
            continue

        links = evidence_links.get(field) or []
        prev = provenance.get(field) if isinstance(provenance.get(field), dict) else {}
        original = prev.get("source") or prev.get("original_source")
        provenance[field] = {
            "source": FieldProvenanceSource.WEB_EVIDENCE.value,
            "final_source": FieldProvenanceSource.WEB_EVIDENCE.value,
            "original_source": original,
            "evidence_ids": links,
            "note": "외부 검색 근거로 보완",
        }

    return provenance

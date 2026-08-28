"""Application-level string enums stored as VARCHAR + CHECK.

Stage and Category are NOT enums — they are Workspace-scoped tables.
"""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    LOCKED = "LOCKED"  # admin lock only; login failure uses locked_until
    WITHDRAWN = "WITHDRAWN"


class SystemRole(StrEnum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    USER = "USER"


class WorkspaceType(StrEnum):
    PERSONAL = "PERSONAL"
    TEAM = "TEAM"


class WorkspaceRole(StrEnum):
    """Maps FE MemberRole: admin/member/readonly → ADMIN/MEMBER/VIEWER."""

    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class WorkspaceMemberStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class IdeaPriority(StrEnum):
    """Maps FE Priority: high/medium/low."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IdeaFeasibility(StrEnum):
    """Maps FE Feasibility: high/medium/low/unknown."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class IdeaVisibility(StrEnum):
    """Maps FE Visibility: private/workspace/specific → PRIVATE/WORKSPACE/SELECTED_USERS."""

    PRIVATE = "PRIVATE"
    WORKSPACE = "WORKSPACE"
    SELECTED_USERS = "SELECTED_USERS"


class IdeaSharePermission(StrEnum):
    READ = "READ"
    EDIT = "EDIT"


# --- Step 7: AI Session / Job ---


class IdeaAiSessionPurpose(StrEnum):
    """Future-ready purposes. Step 7 APIs only execute CREATE."""

    CREATE = "CREATE"
    REFINE = "REFINE"
    RESEARCH = "RESEARCH"


class IdeaAiSessionStatus(StrEnum):
    PROCESSING = "PROCESSING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AiJobType(StrEnum):
    STRUCTURE_IDEA = "STRUCTURE_IDEA"
    WEB_RESEARCH = "WEB_RESEARCH"


class WebResearchRunStatus(StrEnum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    QUEUED = "QUEUED"
    SEARCHING = "SEARCHING"
    REFINING = "REFINING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AiJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class FieldProvenanceSource(StrEnum):
    USER_INPUT = "USER_INPUT"
    LLM_SUMMARY = "LLM_SUMMARY"
    LLM_INFERENCE = "LLM_INFERENCE"
    WEB_EVIDENCE = "WEB_EVIDENCE"
    USER_EDIT = "USER_EDIT"


class AiLlmDecision(StrEnum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"

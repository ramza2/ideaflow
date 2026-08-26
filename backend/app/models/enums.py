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

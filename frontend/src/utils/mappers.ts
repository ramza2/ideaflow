import type {
  IdeaFeasibility,
  IdeaPriority,
  IdeaVisibility,
  WorkspaceMemberStatus,
  WorkspaceRole,
} from "../types/api";
import type { Feasibility, Priority, Visibility } from "../types";

/** UI label mapping for backend enums (display only). */

export const PRIORITY_LABELS: Record<IdeaPriority, string> = {
  HIGH: "높음",
  MEDIUM: "중간",
  LOW: "낮음",
};

export const FEASIBILITY_LABELS: Record<IdeaFeasibility, string> = {
  HIGH: "높음",
  MEDIUM: "중간",
  LOW: "낮음",
  UNKNOWN: "미평가",
};

export const VISIBILITY_LABELS: Record<IdeaVisibility, string> = {
  PRIVATE: "비공개",
  WORKSPACE: "작업공간",
  SELECTED_USERS: "지정 사용자",
};

export const WORKSPACE_ROLE_LABELS: Record<WorkspaceRole, string> = {
  ADMIN: "작업공간 관리자",
  MEMBER: "일반 구성원",
  VIEWER: "읽기 전용",
};

export const MEMBER_STATUS_LABELS: Record<WorkspaceMemberStatus, string> = {
  ACTIVE: "참여 중",
  PENDING: "초대 대기",
  INACTIVE: "비활성",
};

/** Legacy mock enum → backend enum (for AI pages only). */
export function mockPriorityToApi(p: Priority): IdeaPriority {
  return p.toUpperCase() as IdeaPriority;
}

export function mockFeasibilityToApi(f: Feasibility): IdeaFeasibility {
  return f.toUpperCase() as IdeaFeasibility;
}

export function mockVisibilityToApi(v: Visibility): IdeaVisibility {
  if (v === "specific") return "SELECTED_USERS";
  return v.toUpperCase() as IdeaVisibility;
}

export function apiVisibilityToMock(v: IdeaVisibility): Visibility {
  if (v === "SELECTED_USERS") return "specific";
  return v.toLowerCase() as Visibility;
}

export function workspaceIcon(type: "PERSONAL" | "TEAM"): string {
  return type === "PERSONAL" ? "🏠" : "👥";
}

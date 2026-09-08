import type { AiTask, AiTaskType } from "../types/api";

export type AiTaskViewModel = {
  id: string;
  type: AiTaskType;
  ideaId?: string | null;
  ideaTitle: string;
  status: string;
  displayStatus: string;
  typeLabel: string;
  startedAt?: string | null;
  completedAt?: string | null;
  isActive: boolean;
  failureMessage?: string | null;
  href: string | null;
};

const TYPE_LABELS: Record<AiTaskType, string> = {
  CREATE: "아이디어 생성",
  REFINE: "아이디어 보완",
  RESEARCH: "웹 조사",
};

const SESSION_STATUS_LABELS: Record<string, string> = {
  PROCESSING: "분석 중",
  NEEDS_CLARIFICATION: "추가 질문 대기",
  READY_FOR_REVIEW: "검토 준비 완료",
  FAILED: "실패",
  CONFIRMED: "완료",
  CANCELLED: "취소됨",
};

const RESEARCH_STATUS_LABELS: Record<string, string> = {
  QUEUED: "검색 준비 중",
  SEARCHING: "웹 조사 중",
  REFINING: "결과 정리 중",
  READY: "조사 완료",
  FAILED: "조사 실패",
  AWAITING_APPROVAL: "검색 승인 대기",
  CANCELLED: "취소됨",
};

export function aiTaskTypeLabel(type: AiTaskType): string {
  return TYPE_LABELS[type] ?? type;
}

export function aiTaskDisplayStatus(task: Pick<AiTask, "type" | "status">): string {
  if (task.type === "RESEARCH") {
    return RESEARCH_STATUS_LABELS[task.status] ?? task.status;
  }
  return SESSION_STATUS_LABELS[task.status] ?? task.status;
}

export function aiTaskHref(workspaceId: string, task: AiTask): string | null {
  if (!workspaceId) return null;

  if (task.type === "RESEARCH") {
    if (!task.idea_id) return null;
    return `/w/${workspaceId}/ideas/${task.idea_id}?tab=research`;
  }

  if (task.type === "REFINE") {
    if (!task.idea_id) return null;
    if (task.status === "PROCESSING" || task.status === "FAILED") {
      return `/w/${workspaceId}/ideas/${task.idea_id}/ai/refine/${task.session_id}/analyzing`;
    }
    return `/w/${workspaceId}/ideas/${task.idea_id}/ai/refine/${task.session_id}/review`;
  }

  // CREATE
  if (task.status === "PROCESSING" || task.status === "FAILED") {
    return `/w/${workspaceId}/ideas/new/ai/analyzing/${task.session_id}`;
  }
  if (task.idea_id && task.status === "CONFIRMED") {
    return `/w/${workspaceId}/ideas/${task.idea_id}`;
  }
  return `/w/${workspaceId}/ideas/new/ai/review/${task.session_id}`;
}

export function toAiTaskViewModel(workspaceId: string, task: AiTask): AiTaskViewModel {
  return {
    id: task.id,
    type: task.type,
    ideaId: task.idea_id,
    ideaTitle: task.idea_title?.trim() || "제목 없는 아이디어",
    status: task.status,
    displayStatus: aiTaskDisplayStatus(task),
    typeLabel: aiTaskTypeLabel(task.type),
    startedAt: task.started_at,
    completedAt: task.completed_at,
    isActive: task.is_active,
    failureMessage: task.failure_message,
    href: aiTaskHref(workspaceId, task),
  };
}

export function formatRelativeTime(iso: string | null | undefined, nowMs = Date.now()): string {
  if (!iso) return "";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const diffSec = Math.max(0, Math.floor((nowMs - then) / 1000));
  if (diffSec < 60) return "방금 전";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}일 전`;
}

export function completionToastCopy(task: AiTask): { title: string; description?: string } {
  const name = task.idea_title?.trim() || "아이디어";
  if (task.type === "RESEARCH") {
    return { title: "AI 조사가 완료되었습니다.", description: `"${name}"` };
  }
  if (task.type === "REFINE") {
    return { title: "AI 보완이 완료되었습니다.", description: `"${name}"` };
  }
  return { title: "AI 초안 생성이 완료되었습니다.", description: `"${name}"` };
}

export function failureToastCopy(task: AiTask): { title: string; description?: string } {
  const name = task.idea_title?.trim() || "아이디어";
  const detail = task.failure_message?.trim();
  const kind =
    task.type === "RESEARCH" ? "웹 조사" : task.type === "REFINE" ? "보완" : "초안 생성";
  return {
    title: "AI 작업을 완료하지 못했습니다.",
    description: detail ? `"${name}" · ${kind} · ${detail}` : `"${name}" · ${kind}`,
  };
}

export function isTerminalAiTaskStatus(task: Pick<AiTask, "type" | "status" | "is_active">): boolean {
  if (task.is_active) return false;
  if (task.type === "RESEARCH") {
    return task.status === "READY" || task.status === "FAILED";
  }
  return (
    task.status === "READY_FOR_REVIEW" ||
    task.status === "NEEDS_CLARIFICATION" ||
    task.status === "FAILED"
  );
}

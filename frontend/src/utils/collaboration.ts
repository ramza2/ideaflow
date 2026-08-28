import type { NotificationType, ReviewResult } from "../types/api";

export const REVIEW_RESULT_OPTIONS: { value: ReviewResult; label: string }[] = [
  { value: "ADVANCE_RECOMMENDED", label: "다음 단계 권고" },
  { value: "KEEP", label: "현 단계 유지" },
  { value: "HOLD", label: "보류" },
  { value: "NEEDS_INFO", label: "보완 필요" },
];

export const REVIEW_KIND_OPTIONS = [
  { value: "GENERAL" as const, label: "일반 검토" },
  { value: "NEEDS_INFO" as const, label: "내용 보완 필요" },
  { value: "NEXT_STAGE" as const, label: "다음 단계 후보" },
];

export function notificationTitle(type: NotificationType, actorName?: string | null): string {
  switch (type) {
    case "REVIEW_REQUESTED":
      return `${actorName ?? "사용자"}님이 검토를 요청했습니다.`;
    case "REVIEW_COMPLETED":
      return `${actorName ?? "사용자"}님이 검토를 완료했습니다.`;
    case "COMMENT_ADDED":
      return `${actorName ?? "사용자"}님이 댓글을 남겼습니다.`;
    case "MENTION":
      return `${actorName ?? "사용자"}님이 댓글에서 회원님을 언급했습니다.`;
    case "ASSIGNED":
      return "아이디어 담당자로 지정되었습니다.";
    default:
      return "알림";
  }
}

export function notificationBody(ideaCode?: string | null, ideaTitle?: string | null): string {
  if (ideaCode && ideaTitle) return `${ideaCode} · ${ideaTitle}`;
  if (ideaTitle) return ideaTitle;
  return "";
}

export const REVIEW_COUNTS_CHANGED_EVENT = "ideaflow:review-counts-changed";

export function dispatchReviewCountsChanged(): void {
  window.dispatchEvent(new CustomEvent(REVIEW_COUNTS_CHANGED_EVENT));
}

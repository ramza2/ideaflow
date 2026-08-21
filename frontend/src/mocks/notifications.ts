import type { Notification } from "../types";

export const MOCK_NOTIFICATIONS: Notification[] = [
  {
    id: "n-001",
    type: "comment",
    title: "김서연님이 댓글을 달았습니다",
    body: "글로벌 MCP 협업 네트워크 — \"신뢰 모델 부분을 더 구체화하면 어떨까요?\"",
    ideaId: "idea-001",
    createdAt: "2026-07-23T10:30:00Z",
    read: false,
  },
  {
    id: "n-002",
    type: "ai_done",
    title: "AI 분석이 완료되었습니다",
    body: "AI 회의록 정리 서비스 초안이 준비되었습니다. 검토해 주세요.",
    ideaId: "idea-005",
    createdAt: "2026-07-23T09:15:00Z",
    read: false,
  },
  {
    id: "n-003",
    type: "review_due",
    title: "검토 예정 알림",
    body: "그룹웨어 업무지시 자동화의 검토일이 5일 후입니다.",
    ideaId: "idea-008",
    createdAt: "2026-07-23T08:00:00Z",
    read: false,
  },
  {
    id: "n-004",
    type: "assigned",
    title: "담당자로 지정되었습니다",
    body: "사내 문서 검색 서비스의 담당자로 지정되었습니다.",
    ideaId: "idea-004",
    createdAt: "2026-07-22T16:00:00Z",
    read: true,
  },
  {
    id: "n-005",
    type: "workspace_invite",
    title: "작업공간 초대",
    body: "박민준님이 'OpenLink Lab' 작업공간에 초대했습니다.",
    createdAt: "2026-07-21T11:00:00Z",
    read: true,
  },
];

# IdeaFlow notes

## Step 19 — AI 작업 상태 / 완료 알림

- Source of truth: Backend `IdeaAiSession` + `WebResearchRun` (no `ai_tasks` table).
- API: `GET /api/v1/workspaces/{workspace_id}/ai-tasks`
- Frontend: Header `AiTasksIndicator` + `AiTasksProvider` polling (~4s).
- AI Task UI stores **status/metadata only**, not research result payloads.

## Follow-up TODO (Step 20+)

F5/재진입 후에도 조사 결과가 유지되도록 Research 결과 서버 영속 저장 및 Idea 상세 재조회/복원 흐름 구현.

대상:

- 조사 요약
- 상세 조사 결과
- 근거 자료 / 출처
- 최신 Research 상태

주의: 전역 AI Task 알림과 Research 결과 데이터 책임을 분리할 것.

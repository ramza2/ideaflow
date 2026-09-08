# IdeaFlow notes

## Step 19 — AI 작업 상태 / 완료 알림

- Source of truth: Backend `IdeaAiSession` + `WebResearchRun` (no `ai_tasks` table).
- API: `GET /api/v1/workspaces/{workspace_id}/ai-tasks`
- Frontend: Header `AiTasksIndicator` + `AiTasksProvider` polling (~4s).
- AI Task UI stores **status/metadata only**, not research result payloads.

## Follow-up TODO (Step 20+)

F5/재진입 후에도 조사 결과가 유지되도록 Research 결과 서버 영속 저장 및 Idea 상세 재조회/복원 흐름 구현.

→ **Step 20에서 구현됨.** 상세: `docs/step-20-research-persistence.md`

남은 확장:

- Research history UI
- 이전 조사 버전 비교
- source별 상세 provenance UI
- Semantic / Hybrid Search UI

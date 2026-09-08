# Step 20 — Research 결과 영속화 및 F5/재진입 복원

## 설계

- Source of Truth: 기존 `web_research_runs.research_summary` / `result_count` / `completed_at` + `web_evidence`
- 새 DB 테이블/컬럼 없음 (이미 worker가 READY와 동시에 summary를 저장)
- Idea 상세 복원 API: `GET /workspaces/{ws}/ideas/{idea_id}/research-runs/latest`
  - Idea read ACL
  - 최신 READY run (CONFIRMED session의 `result_idea_id`)
  - 과거 READY run 보존 (overwrite 금지)

## Frontend

- Research 탭 mount 시 latest READY + evidence 조회
- 진행 중 session은 기존 `research-sessions/latest` + `useWebResearch` 유지
- `displayResearchRun = live ?? persisted`

## 후속 TODO

- Research history UI (이전 조사 목록 / 버전 비교)
- source별 상세 provenance UI
- Semantic / Hybrid Search UI

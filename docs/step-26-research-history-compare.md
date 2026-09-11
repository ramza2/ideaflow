# Step 26 — Research History / Version Compare UI

## Data source

- **No new tables / no migration.** History is derived from existing `web_research_runs` + `web_evidence`.
- Only **READY** runs linked via CONFIRMED `idea_ai_sessions.result_idea_id` are history versions.
- FAILED / SEARCHING / AWAITING_APPROVAL runs are excluded from history (failed follow-up must not hide prior READY).

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/workspaces/{ws}/ideas/{idea_id}/research-runs` | Lightweight READY history (`evidence_count`, `query_count`, `is_latest`) |
| `GET` | `/workspaces/{ws}/ideas/{idea_id}/research-runs/latest` | Unchanged — F5 / re-entry restore of latest READY |
| `GET` | `/workspaces/{ws}/ideas/{idea_id}/research-runs/{run_id}` | One READY run with summary, queries, per-run evidence |

ACL: same Idea read ACL as latest (`get_readable_idea`). `run_id` alone cannot cross Idea / workspace.

Ordering: `completed_at DESC NULLS LAST`, `created_at DESC`. Pagination: `limit` (default 20) / `offset`.

## History policy

```text
포함 status: READY only
정렬: completed_at DESC, created_at DESC
latest 기준: 동일 정렬의 첫 READY (실행 중 SEARCHING은 무시)
version 계산: UI에서 oldest READY = v1 … newest = vN (DB version 컬럼 없음)
```

## Compare

- Frontend deterministic compare (no compare API, no LLM diff).
- Evidence identity: normalized URL (`trim` / lower / drop `#fragment` / strip trailing `/`).
- Buckets: **added** / **removed** / **unchanged** (+ optional metadata-changed note).
- Summary: side-by-side only.
- MVP compare entry: past version ↔ latest READY.

## UI

- Research tab keeps current latest result + evidence list.
- Below: **조사 이력** list with version badge, completed time, evidence/query counts, 보기 / 최신과 비교.
- Detail & compare use modal overlays (not URL state). F5 restores history from API; modal state is ephemeral.
- Mobile: compare stacks vertically (`grid-cols-1 md:grid-cols-2`).

## Polling / refetch

- No new polling engine.
- History fetch: mount / idea change / when live research transitions to READY (`refreshKey`).
- Idea change resets list + closes modals (no stale cross-idea flash).

## F5 / failed follow-up

- F5: latest READY + history reload from DB.
- Failed newer run: still absent from history; previous READY remains latest.

## Remaining TODO (non-blocking)

- FAILED history display → future
- Free A/B picker beyond past↔latest → future
- URL `?compare=` persistence → not required
- LLM “what changed” summary → out of scope

## Migration

```text
Migration: none
```

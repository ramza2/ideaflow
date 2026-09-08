# Step 21 — Semantic / Hybrid Search UI

Idea 목록에서 기존 Backend `search_mode` API(`keyword` / `semantic` / `hybrid`)를 Frontend에 연결한다.

## Backend (재사용)

- Endpoint: `GET /api/v1/workspaces/{workspace_id}/ideas?q=&search_mode=`
- Keyword: ILIKE + FTS(`simple`), `updated_at` 정렬
- Semantic: query embedding → pgvector cosine distance (embedding enabled 필요)
- Hybrid: Reciprocal Rank Fusion (`RRF_K=60`), 상위 300 window
- 오류: `SEMANTIC_SEARCH_UNAVAILABLE`, `HYBRID_RESULT_WINDOW_EXCEEDED`, `INVALID_SEARCH_MODE`

## Frontend

- Idea 목록 segmented control: 키워드 / 의미 검색 / 하이브리드
- URL: `q`, `search_mode`(non-keyword), 기존 필터/offset 유지
- 기본 모드: `keyword` (`VITE_IDEA_SEARCH_MODE`로 override 가능)
- Hybrid + semantic unavailable → keyword fallback + 안내
- Semantic + unavailable → 오류 + 「키워드 검색으로 다시 보기」(위장하지 않음)

## 범위 밖

- embedding backfill UI, ranking 튜닝, search history/saved search, 결과 explainability

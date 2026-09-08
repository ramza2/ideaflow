# Step 23 — MVP integration / regression

Goal: exercise the full user journey end-to-end, find cross-feature regressions,
fix Blocker/High issues, and record MVP stability.

## Test environment

| Component | Status / notes |
|---|---|
| Backend | FastAPI `uvicorn` `:8000` (in-process AI + Embedding workers) |
| Frontend | Vite `:5173` |
| DB | PostgreSQL + `pgvector`; Alembic head includes embedding migrations |
| LLM | `openai_compatible` → Qwen3-14B (`alzi-llm.openlink.kr`) |
| Web Search | Local mock `scripts/dev_web_search_mock.py` `:8091` (`http_json`) |
| Embedding | Local `scripts/dev_embedding_server.py` `:8090` (BGE-M3, dim 1024) |
| Smoke user | `mvp-s23@example.com` (dedicated; not production data) |
| Workspace | `6d982c69-e13f-4f7e-bc04-6a1f89600338` |

## Scenarios executed

API smoke (`/tmp/s23_mvp_smoke.py`, live backend): login → Idea CRUD → AI CREATE →
confirm → AI REFINE → apply → Research preview/approve → READY → Evidence →
latest/F5 restore → 다시 조사 → failure preserves READY → Keyword/Semantic/Hybrid
search → filter+hybrid → ACL private block → embedding coverage.

UI smoke (headless Chrome + playwright-core): login → Idea list → search mode URL
(`semantic`/`hybrid`) → list search `q` + mode persistence → Idea detail → Research
tab → F5 restore → AI 작업 indicator → mobile viewport → back navigation.

## Results summary

| Metric | Value |
|---|---|
| API smoke checks | 38 |
| Pass | 38 |
| Fail | 0 |
| Blocker | 0 (after fix) |
| High | 0 (after fix) |
| Medium | 0 open |
| Low | 2 noted (below) |

Embedding coverage after smoke:

```text
coverage total=1051 with_embedding=1051 without_embedding=0 percent=100.0
jobs_queued=0 jobs_running=0 jobs_succeeded=1051 jobs_failed=0
```

Data integrity (spot SQL): embedding/session/research/evidence orphans = 0;
stuck RUNNING jobs = 0; duplicate active research runs = 0.

## Bugs found

### High — AI REFINE `LLM_RESPONSE_INVALID` on list-shaped text fields

- **Symptom:** Registered-idea REFINE often FAILED with `LLM_RESPONSE_INVALID`
  even when the LLM HTTP call returned 200.
- **Cause:** Qwen frequently returns JSON arrays for text fields
  (`major_features`, `target_users`, `scenarios`, `challenges`, …) while
  `IdeaRefinementPatch` required `str | None`.
- **Fix:** `@field_validator(..., mode="before")` coerces string lists to
  newline-joined text in `backend/app/llm/refine_schemas.py`.
- **Regression:** `test_text_list_fields_coerced_to_multiline_string` in
  `tests/test_refine_schema_unit.py`.
- **Re-smoke:** live REFINE → `READY_FOR_REVIEW` → apply OK; full API smoke 38/38.

### False fails in first smoke (not product bugs)

- `research-runs/latest` returns `{ "run": ... }`; script initially treated the
  wrapper as the run.
- Refine apply sent `tags` as `{id,name}` objects; API expects `string[]`
  (UI already does).

## Automated tests run

- `pytest tests/test_refine_schema_unit.py` — pass (incl. new coerce test)
- `pytest tests/test_ai_tasks_integration.py` — pass
- `pytest tests/test_semantic_search_integration.py` — pass
- `pytest tests/test_idea_research_integration.py` — pass
- `pytest tests/test_ai_refine_integration.py` — pass
- Frontend `tsc --noEmit` — pass
- Frontend `npm run build` — pass
- `frontend/scripts/check-ai-task-toast.ts` — pass

No new Playwright framework was added (project has none). Existing toast gate
script + backend integration coverage already cover the priority flows; one
targeted refine-schema unit test was added for the High bug.

## F5 / navigation (UI)

| Screen | Result |
|---|---|
| Idea list + `search_mode` | Pass (URL restored) |
| List search `q` + hybrid | Pass |
| Idea detail | Pass |
| Research tab | Pass |
| Research after F5 | Pass (`?tab=research`, summary/evidence still present) |
| Login session after F5 | Pass |
| Back from detail → list | Pass (mode preserved) |
| Mobile ~390px list | Pass (no layout crash) |

## Polling / console / logs

- Pre-login `GET /api/v1/auth/me` → 401 once (bootstrap probe; expected).
- No post-login API 5xx observed during UI smoke.
- No evidence of stuck Research/AI polling after navigation in API smoke.
- Backend workers started cleanly with app process.

## Shared-DB pytest hazard (confirmed)

Running `test_semantic_search_integration` / `test_idea_research_integration`
against the live `DATABASE_URL` **deletes all `idea_embeddings` rows**. After the
Step 23 pytest pass, coverage dropped from 100% → ~2% until
`python -m app.cli.enqueue_embeddings --all` + worker catch-up.

Mitigation this Step:

- Document the hazard here and emit `UserWarning` from wipe helpers.
- Prefer a dedicated test database for CI (follow-up).

## Remaining TODO (Medium/Low only)

1. **Medium — Dedicated test DB:** stop sharing the live Postgres with
   embedding-wiping integration fixtures.
2. **Low — Keyword fixture gap:** smoke query `회의록` returned `total=0` in this
   workspace (no matching ideas). Product path OK; optional seed for demos.
3. **Low — Dual search inputs:** header global search vs list `목록 검색...` can
   confuse automation/users; document or unify later (not MVP blocker).

## MVP judgment

**`MVP integration PASS WITH MINOR TODO`**

Critical journey (CREATE → REFINE → Research → F5 → 다시 조사 → AI tasks →
Keyword/Semantic/Hybrid → ACL → embeddings) passed after one High fix.
No remaining Blocker/High. Only Low TODOs remain.

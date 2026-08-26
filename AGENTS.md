# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

IdeaFlow is a natural-language idea-management product. The `frontend/` is an approved Figma Make UI prototype wired to the Backend API (Step 6). The `backend/` FastAPI service includes foundation through Idea CRUD/ACL/search plus Step 7 AI Session/Job/LLM provider (Frontend AI pages still mock).

- `frontend/` — Vite 6 + React 18 + TypeScript UI, generated from Figma Make (Tailwind CSS v4, MUI, Radix/shadcn components). Auth, Workspace, Members, and Manual Idea CRUD use real APIs; AI/Review pages remain mock until Step 8.
- `backend/` — FastAPI + SQLAlchemy 2 + Alembic + Auth + Workspace RBAC + Ideas + **AI Sessions/Jobs** (`/api/v1/health`, `/api/v1/auth/*`, `/api/v1/workspaces/*`, `/ideas`, `/ai-sessions`).

### Frontend service

- Package manager is **npm** (there is a `frontend/package-lock.json`). Although a `pnpm-workspace.yaml` and a `pnpm` overrides block also exist in `frontend/`, the committed lockfile is npm's, so use `npm` to stay consistent. All commands must be run from the `frontend/` directory.
- Dev server: `npm run dev` (Vite, serves on `http://localhost:5173`; proxies `/api` → Backend).
- Typecheck: `npm run typecheck` (`tsc --noEmit`).
- Production build: `npm run build` (outputs to `frontend/dist/`).
- There is **no lint or test script** in `package.json`. Do not expect `npm run lint` or `npm test` to exist.

### Backend service

- Python **3.11+**. Work from the `backend/` directory.
- Install: `pip install -e ".[dev]"`
- Dev server: `uvicorn app.main:app --reload` (default `http://127.0.0.1:8000`)
- Tests: `pytest` (DB integration tests require `DATABASE_URL`)
- Health: `GET /api/v1/health`
- Auth: session cookie (`ideaflow_session`) + CSRF (`ideaflow_csrf` / `X-CSRF-Token`); bootstrap admin via `python -m app.cli.create_admin` (also provisions Personal Workspace)
- Workspaces: Personal ensure / Team create / member RBAC; backfill via `python -m app.cli.ensure_personal_workspaces`
- Ideas: workspace-scoped CRUD + ACL + `?q=` ILIKE/FTS search
- AI (Step 7): `IdeaAiSession` + `AiJob` PostgreSQL queue; in-process worker (`AI_WORKER_ENABLED`); OpenAI-compatible LLM via `httpx`; probe with `python -m app.cli.llm_probe`. Tests should set `AI_WORKER_ENABLED=false`.
- Migrations (PostgreSQL required):

```text
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
export AI_WORKER_ENABLED=false
alembic upgrade head
pytest
```

### Non-obvious behavior

- **Auth / Workspace / Manual Idea flows use the real Backend** (HttpOnly session + CSRF cookie). Dev: Browser calls `http://localhost:5173/api/v1/...` via Vite proxy. Legacy route `/w/personal/*` redirects to the user's PERSONAL workspace UUID.
- **AI Input / Analyzing / Review, Reviews inbox, notifications, and help content remain mock/prototype** until later steps.
- Routing uses `react-router` `createBrowserRouter`. The root path `/` redirects to `/login`; the main app lives under `/w/:workspaceId/...` (workspaceId is a Backend UUID; `/w/personal/*` is legacy-compatible).
- The Vite config includes a custom `figma:asset/` import resolver, `@` alias, and `/api` dev proxy.
- Root `.env.example` includes `VITE_API_BASE_URL`, `VITE_AUTH_CSRF_COOKIE_NAME`, `VITE_DEV_API_PROXY_TARGET`, plus backend placeholders. Backend Settings load the repository-root `.env` (cwd-independent).

### UI preservation

- The current frontend was generated from the approved Figma Make prototype and is the visual/UX baseline for IdeaFlow.
- Preserve the existing layout, navigation, typography, colors, component styling, and user flows unless a task explicitly requests a design change.
- When replacing mock behavior with real backend/API behavior, prefer adapting data and state layers rather than redesigning the UI.
- Do not perform large-scale frontend refactoring solely for stylistic or architectural preference.

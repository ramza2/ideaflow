# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

IdeaFlow is a natural-language idea-management product. The `frontend/` is an approved Figma Make UI prototype. The `backend/` FastAPI service currently provides a Step 1 foundation (health/config/logging only). `docs/` is still a placeholder. Database, Auth, Workspace, Idea, and LLM features are not implemented yet.

- `frontend/` — Vite 6 + React 18 + TypeScript UI, generated from Figma Make (Tailwind CSS v4, MUI, Radix/shadcn components).
- `backend/` — FastAPI foundation (`GET /api/v1/health`). No DB/Auth/LLM yet.

### Frontend service

- Package manager is **npm** (there is a `frontend/package-lock.json`). Although a `pnpm-workspace.yaml` and a `pnpm` overrides block also exist in `frontend/`, the committed lockfile is npm's, so use `npm` to stay consistent. All commands must be run from the `frontend/` directory.
- Dev server: `npm run dev` (Vite, serves on `http://localhost:5173`).
- Production build: `npm run build` (outputs to `frontend/dist/`).
- There are **no lint or test scripts** defined in `package.json` (only `dev` and `build`), and there is no ESLint/TypeScript config file — Vite/esbuild transpiles `.tsx` without type-checking. Do not expect `npm run lint` or `npm test` to exist.

### Backend service

- Python **3.11+**. Work from the `backend/` directory.
- Install: `pip install -e ".[dev]"`
- Dev server: `uvicorn app.main:app --reload` (default `http://127.0.0.1:8000`)
- Tests: `pytest`
- Health: `GET /api/v1/health`

### Non-obvious behavior

- **The frontend is still a mock-only prototype with no backend persistence wired.** Data comes from static fixtures in `frontend/src/mocks/`. Actions like login and saving an idea are simulated:
  - The login page (`/login`) accepts **any password except the literal string `wrong`** (which triggers an error state) and then navigates to `/w/personal/home`.
  - Saving a new idea (`handleSave` in `src/pages/ideas/IdeaEditPage.tsx`) only shows a success toast (`아이디어가 등록되었습니다`) and navigates to a hardcoded idea (`/w/.../ideas/idea-001`). Nothing is persisted and the ideas count does not change. This is expected behavior, not a bug.
- Routing uses `react-router` `createBrowserRouter`. The root path `/` redirects to `/login`; the main app lives under `/w/:workspaceId/...` (e.g. `/w/personal/home`, `/w/personal/ideas`).
- The Vite config includes a custom `figma:asset/` import resolver and aliases `@` to `frontend/src`.
- Root `.env.example` includes shared app/backend placeholders (DATABASE_URL, LLM_*, WEB_SEARCH_*, CORS_ORIGINS). The frontend does not consume them yet; the backend Step 1 app uses APP_* / LOG_LEVEL / CORS_ORIGINS / API_V1_PREFIX only.

### UI preservation

- The current frontend was generated from the approved Figma Make prototype and is the visual/UX baseline for IdeaFlow.
- Preserve the existing layout, navigation, typography, colors, component styling, and user flows unless a task explicitly requests a design change.
- When replacing mock behavior with real backend/API behavior, prefer adapting data and state layers rather than redesigning the UI.
- Do not perform large-scale frontend refactoring solely for stylistic or architectural preference.

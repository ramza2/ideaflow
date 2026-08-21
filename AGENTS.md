# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

IdeaFlow is a natural-language idea-management product. This repo currently contains only a **frontend prototype**; the `backend/` directory is an empty placeholder (`.gitkeep`) with no code, and `docs/` is empty as well. All development work today happens in `frontend/`.

- `frontend/` — Vite 6 + React 18 + TypeScript UI, generated from Figma Make (Tailwind CSS v4, MUI, Radix/shadcn components). This is the only runnable service.
- `backend/` — placeholder only, nothing to install or run yet.

### Frontend service

- Package manager is **npm** (there is a `frontend/package-lock.json`). Although a `pnpm-workspace.yaml` and a `pnpm` overrides block also exist in `frontend/`, the committed lockfile is npm's, so use `npm` to stay consistent. All commands must be run from the `frontend/` directory.
- Dev server: `npm run dev` (Vite, serves on `http://localhost:5173`).
- Production build: `npm run build` (outputs to `frontend/dist/`).
- There are **no lint or test scripts** defined in `package.json` (only `dev` and `build`), and there is no ESLint/TypeScript config file — Vite/esbuild transpiles `.tsx` without type-checking. Do not expect `npm run lint` or `npm test` to exist.

### Non-obvious behavior

- **The app is a mock-only prototype with no backend/persistence.** Data comes from static fixtures in `frontend/src/mocks/`. Actions like login and saving an idea are simulated:
  - The login page (`/login`) accepts **any password except the literal string `wrong`** (which triggers an error state) and then navigates to `/w/personal/home`.
  - Saving a new idea (`handleSave` in `src/pages/ideas/IdeaEditPage.tsx`) only shows a success toast (`아이디어가 등록되었습니다`) and navigates to a hardcoded idea (`/w/.../ideas/idea-001`). Nothing is persisted and the ideas count does not change. This is expected behavior, not a bug.
- Routing uses `react-router` `createBrowserRouter`. The root path `/` redirects to `/login`; the main app lives under `/w/:workspaceId/...` (e.g. `/w/personal/home`, `/w/personal/ideas`).
- The Vite config includes a custom `figma:asset/` import resolver and aliases `@` to `frontend/src`.
- `.env.example` at the repo root references future backend concerns (DATABASE_URL, LLM_API_URL, WEB_SEARCH_API_*). These are not consumed by the current frontend and are not required to run it.

### UI preservation

- The current frontend was generated from the approved Figma Make prototype and is the visual/UX baseline for IdeaFlow.
- Preserve the existing layout, navigation, typography, colors, component styling, and user flows unless a task explicitly requests a design change.
- When replacing mock behavior with real backend/API behavior, prefer adapting data and state layers rather than redesigning the UI.
- Do not perform large-scale frontend refactoring solely for stylistic or architectural preference.

# IdeaFlow

자연어로 입력한 아이디어를 LLM과 웹 검색으로 구조화하고 여러 사용자가 관리·발전시키는 범용 아이디어 관리 서비스

## 디렉터리 구조

```text
IdeaFlow/
├─ frontend/   # Figma Make 기반 Vite/React UI
├─ backend/    # FastAPI Backend
└─ docs/       # 설계 및 프로젝트 문서
```

## 현재 상태

- Frontend: Figma Make UI + **Backend API 연동 (Step 6)** — Login, Workspace, Members, Manual Idea CRUD/Search
- Backend: Auth + Workspace RBAC + Idea CRUD/ACL/search + **AI Session/Job/LLM provider (Step 7)**
- Frontend AI Input/Analyzing/Review 페이지는 아직 mock (Step 8에서 연결)

## 개발 실행

PostgreSQL과 Backend를 먼저 실행한 뒤 Frontend dev server를 띄웁니다.

```bash
# Backend (터미널 1)
cd backend
export DATABASE_URL=postgresql+psycopg://ideaflow:ideaflow@localhost:5432/ideaflow
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (터미널 2)
cd frontend
npm install
npm run dev
```

브라우저: `http://localhost:5173`

Frontend는 `/api/v1/...`를 호출하며, Vite dev server가 `/api`를 `http://127.0.0.1:8000`으로 프록시합니다. Auth는 HttpOnly session cookie + JS-readable CSRF cookie(`ideaflow_csrf`) + `X-CSRF-Token` 헤더를 사용합니다.

Frontend 검증:

```bash
cd frontend
npm run typecheck
npm run build
```

자세한 Backend 실행 방법은 `backend/README.md`를 참고하십시오.

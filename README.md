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

- Frontend: Figma Make UI + Backend API 연동 — Login, Workspace, Members, Manual Idea CRUD/Search + **AI Session workflow (Step 8)** + **Web Research approval flow (Step 9)** + **Review / Comment / Notification (Step 10)** + **Admin / SystemSetting (Step 11)** + **Idea Validation tab (Step 14)**
- Backend: Auth + Workspace RBAC + Idea CRUD/ACL/search + AI Session/Job/LLM provider (Step 7) + **Web Research / Evidence (Step 9)** + **Review / Comment / In-app Notification (Step 10)** + **Admin / SystemSetting / Integration diagnostics (Step 11)** + **pgvector Semantic/Hybrid Search (Step 13)** + **Idea Validation (Step 14)** + **Tavily Web Search provider (Step 15)**
- Step 8: Frontend AI Input → processing polling → clarification → review → confirm → Idea 연결 완료
- Step 9: Review 단계에서 승인된 Web Search → Evidence 저장 → Qwen 근거 기반 초안 보완 → Idea Detail 조사 및 근거 탭
- Step 10: Review Request / Inbox, Comment + @Mention, In-app Notification (Bell). Review/Mention/Assignee는 Idea read ACL을 부여하지 않음. Email/Push 없음.
- Step 11: SYSTEM_ADMIN Admin Console (사용자 관리, SystemSetting 4개 정책, Integration diagnostics). Connection config는 ENV read-only; API key DB 저장/노출 없음. Workspace `effective_allow_llm` / `effective_allow_web_search`.
- Step 12: Docker Compose 배포 패키징 (`compose.yaml`, Nginx SPA + API proxy, `scripts/deploy.sh`).
- Step 13: pgvector semantic / hybrid idea search + BGE-M3-compatible embedding provider (`EMBEDDING_*`, default disabled).
- Step 14: Idea Validation workflow (DRAFT→READY→RUNNING→COMPLETED/CANCELLED). Idea Detail **검증** 탭. ACL은 parent Idea. Start 시 `validation_candidate`→`validating`만 자동 이동.
- Step 15: Tavily Web Search Provider (`WEB_SEARCH_PROVIDER=tavily`). Step 9 approval workflow 유지; production 외부 검색 연결. Refinement는 `WEB_RESEARCH_REFINE_*`로 LLM 입력만 제한(저장 Evidence는 전량 유지).
- Step 16: AI Review **임시 저장** (`PUT .../review-draft`) + reload 복구 (`review_state`, `draft_payload`). **전체 다시 생성**은 새 CREATE AiSession 생성(원본 session/research/evidence 보존, Web Search 자동 실행 없음).

## Docker Compose 배포

```bash
git clone https://github.com/ramza2/ideaflow.git
cd ideaflow
./scripts/deploy.sh
```

첫 실행 시 interactive setup wizard가 `.env` 생성, migration, 초기 `SYSTEM_ADMIN` 생성까지 진행합니다.

- **Direct (mini PC / LAN):** [docs/deployment.md](docs/deployment.md)
- **Traefik (GPU server):** [docs/deployment.md#traefik-deployment](docs/deployment.md#traefik-deployment)

고급 사용자는 `cp deploy/.env.example .env` 후 수동 설정도 가능합니다.

## Step 11 — Admin / SystemSetting

- **SystemSetting (DB):** `GLOBAL_LLM_ENABLED`, `GLOBAL_WEB_SEARCH_ENABLED`, `DEFAULT_TEAM_ALLOW_LLM`, `DEFAULT_TEAM_ALLOW_WEB_SEARCH` (boolean only; migration seed 없음).
- **Connection config (ENV):** LLM/Web Search URL·key·provider는 환경변수 authority; Admin에서 read-only 조회 및 diagnostic test만.
- **Global policy:** 새 AI session/clarification/retry 및 web research preview/approve/retry 차단; confirm·read·cancel은 허용.
- **Effective capabilities:** `effective_allow_llm = workspace.allow_llm ∧ GLOBAL_LLM_ENABLED`; web search는 LLM global도 필요.

## Step 10 — Review / Comment / Notification

- **Review ACL:** Reviewer는 기존 Idea read ACL을 가진 ACTIVE workspace member만 지정 가능. Review 완료는 `Idea.stage_id` / `next_review_date`를 자동 변경하지 않음 (`suggested_next_review_date`만 저장).
- **Comment ACL:** Idea read 권한 + ACTIVE member. Mention은 read ACL 대상만 가능하며 Share를 생성하지 않음.
- **Notification:** DB에 관계 ID만 저장; list/unread 시 현재 Idea read ACL 재검증. Revoked ACL notification leak 방지.

## Step 9 — Web Research architecture

- **Approval boundary:** `POST .../research-runs/preview`는 외부 검색을 수행하지 않습니다. 사용자 승인(`approve`) 후 Worker만 Web Search Provider(`http_json` 또는 `tavily`)를 호출합니다.
- **Privacy:** Web Search Provider에는 승인·sanitize된 `query`와 `max_results`만 전송합니다. `input_text`와 전체 AI draft는 외부로 보내지 않습니다.
- **Provider contract:** `http_json` — `POST WEB_SEARCH_API_URL` with JSON `{"query", "max_results"}`; `tavily` — `POST https://api.tavily.com/search` with Tavily Search fields (`search_depth=basic`, etc.). Response maps `content` → `snippet`.
- **Evidence:** Search snippet metadata만 DB 저장 (전체 HTML/기사 본문 저장 금지). Confirmed Idea는 `GET /ideas/{id}/evidence` (Idea read ACL). Confirmed Idea re-research ("다시 조사")는 미구현.
- **Probe:** `python -m app.cli.web_search_probe` (`WEB_SEARCH_API_URL` 미설정 시 `not_configured`).

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

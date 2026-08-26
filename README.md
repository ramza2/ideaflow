# IdeaFlow

자연어로 입력한 아이디어를 LLM과 웹 검색으로 구조화하고 여러 사용자가 관리·발전시키는 범용 아이디어 관리 서비스

## 디렉터리 구조

```text
IdeaFlow/
├─ frontend/   # Figma Make 기반 Vite/React UI
├─ backend/    # FastAPI Backend (Step 4: Workspace RBAC)
└─ docs/       # 설계 및 프로젝트 문서
```

## 현재 상태

- Frontend: Figma Make Prototype (Mock UI; Auth/Workspace 연동은 Step 6)
- Backend: Step 4 — Workspace provisioning + RBAC (Idea/LLM API 미구현)

자세한 Backend 실행 방법은 `backend/README.md`를 참고하십시오.

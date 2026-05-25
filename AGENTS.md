# AGENTS.md — DirectPilot AI contributor guide for Codex

## 1) Project overview
DirectPilot AI is an AI SaaS MVP for **Yandex Direct** audit, monitoring, and optimization.

Primary product goal for MVP:
- User adds a client.
- User connects Yandex Direct + Yandex Metrica via OAuth.
- System syncs **read-only** advertising and analytics data.
- System generates AI recommendations with evidence.
- User reviews and explicitly approves/rejects suggested changes.

**Critical product rule:** direct write actions must never be applied automatically without explicit approval.

---

## 2) Current stack
- Frontend: static prototype + vanilla JS
  - `index.html`, `login.html`, `app.html`
  - `src/main.js`, `src/data.js`, `src/styles.css`
- Backend: FastAPI under `backend/app`
- ORM: SQLAlchemy models
- DB: optional PostgreSQL (when configured)
- AI provider access: backend-only endpoints

---

## 3) MVP user flow
1. User opens cabinet.
2. User adds client (name + Direct login + Metrica counter id).
3. User connects Yandex OAuth account.
4. Backend syncs read-only campaign/goals/metrics data.
5. AI recommendations are generated from backend context.
6. User reviews evidence and preview.
7. User approves/rejects actions.
8. Audit log stores workflow events.

---

## 4) Safety rules
1. **Never commit secrets** (API keys, OAuth tokens, DB passwords, private credentials).
2. **Never expose secrets to frontend**.
3. All Yandex/OpenRouter calls must go through backend.
4. No direct write/apply action without explicit approval.
5. Preserve read-only mode for integrations until guarded write flow is approved.
6. Keep clear fallback behavior when backend integrations are unavailable.

---

## 5) Development commands
From repository root:
- Frontend/static validation build:
  - `npm run build`
- Local frontend dev:
  - `npm run dev`

Backend setup/run:
- `cd backend`
- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`
- `uvicorn app.main:app --reload --port 8000`

Backend checks/tests (when present):
- `python -m compileall backend/app`
- `pytest -q`

---

## 6) Backend rules
- Keep business logic in services, not in routers.
- Keep routers thin: validate input, call service, return response.
- Preserve API compatibility for current frontend where possible.
- Token handling must remain backend-only and encrypted at rest where implemented.
- All external API/network integrations must handle timeouts and errors clearly.
- Approval workflow must remain explicit and auditable.

---

## 7) Frontend rules
- Frontend is vanilla JS (no React/Next migration in MVP).
- Do not move secrets to frontend or localStorage.
- Prefer minimal, safe changes that preserve current UX flows.
- Keep forms stable: avoid rerender patterns that break input interaction.
- API calls should target backend endpoints only.

---

## 8) Database rules
- SQLAlchemy models are source of truth for persistence shape.
- Additive schema changes preferred for MVP stability.
- Keep sync/workflow state queryable (`preview`, `approval`, `audit`, `impact`, client sync fields).
- Never store plaintext secrets/tokens.

---

## 9) AI/LLM rules
- LLM usage only through backend APIs.
- OpenRouter API key must never be committed or exposed to client.
- AI outputs are recommendations/drafts, not automatic execution.
- Recommendation responses should include evidence and next step guidance.
- Maintain deterministic fallback when LLM provider is unavailable.

---

## Project Plan
- Before implementation, read `PROJECT_PLAN.md` and follow its roadmap, safety rules, and current priority order.

---

## Codex Agent Briefs
- For large tasks, read the relevant brief from `.codex/agents/` before planning or editing.
- If callable subagents are not available in the current Codex environment, apply the relevant brief directly.
- Use `ui-designer` for UX audits and visual hierarchy; `frontend-developer` for `src/main.js` frontend implementation; `backend-architect` for FastAPI/DB/API/Yandex work; `code-reviewer` before PRs or after large changes; `debugger` for failures and regressions.

---

## 10) How Codex should work on tasks
- Prefer small, focused PRs over giant patches.
- First stabilize critical paths (client add, sync, AI chat, approval flow), then extend features.
- Always run relevant checks before finalizing.
- When fixing bugs, include or update tests when feasible.
- Keep README/AGENTS instructions aligned with actual behavior.
- If uncertain about scope, choose MVP-safe, least-risk implementation.

---

## 11) What is out of scope for MVP
- Full autonomous optimization without approval.
- Large frontend framework migration.
- Complex multi-tenant enterprise RBAC redesign beyond current MVP needs.
- Broad CRM marketplace integrations before Direct/Metrica core is stable.
- Expensive fine-tuning pipelines before baseline data quality and evaluation are stable.

MVP focus remains: **client onboarding → secure integrations → read-only sync → AI recommendations with evidence → approval workflow → auditability**.

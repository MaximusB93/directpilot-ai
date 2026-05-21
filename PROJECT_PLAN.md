# DirectPilot AI Project Plan

## 1. Product Summary

DirectPilot AI is an AI-powered SaaS MVP for Yandex Direct optimization.

The product helps users:
- connect Yandex Direct and Yandex Metrika;
- load advertising performance data;
- analyze campaign performance;
- evaluate conversions by selected Yandex Metrika goal IDs;
- detect campaign problems;
- generate safe optimization recommendations;
- prepare manual action drafts;
- eventually support approval-based optimization actions.

The product is not a general dashboard. It is an AI assistant for performance marketing analysis and optimization.

## 2. Current Implemented State

The project currently has:

### Frontend
- Static frontend hosted on GitHub Pages.
- Main app page: app.html.
- Login page: login.html.
- Main app logic in src/main.js.
- Standalone login script in src/login.js.
- Backend API base defaults to:
  https://directpilot-ai.vercel.app/api/v1
  when opened from GitHub Pages.
- Backend API URL can still be overridden via localStorage/directpilot_api_base.
- Input/focus bugs in app and login have been fixed.
- App redirects unauthenticated users to login.html.
- Logout button exists.
- Client state is scoped by logged-in email.
- AI chat/recommendation state is scoped by selected client.
- Dashboard includes MVP readiness and sync center.
- Optimization workspace exists.
- AI recommendations page exists.
- Per-client Yandex binding UI exists.

### Backend
- FastAPI backend deployed on Vercel.
- Email code login exists.
- Email sessions are stored in the database.
- API requests use Authorization: Bearer <session_token>.
- /auth/me returns authenticated user information.
- One email = one workspace/organization for MVP.
- Clients are scoped by authenticated user organization.
- Yandex OAuth works.
- Yandex connected accounts are scoped by organization/workspace.
- A Yandex account must be explicitly bound to a client.
- Client sync requires a bound Yandex account.
- Client delete endpoint exists.
- Client settings exist:
  - name
  - direct_login
  - metrica_counter
  - yandex_account_id
  - target_cpa
  - main_goal_id
  - notes
- Safe MVP schema patches are used in backend/app/db.py.
- Sync jobs are stored.
- Direct campaign period stats are stored.
- Performance summary endpoint exists.
- Optimization plan endpoint exists.
- AI recommendations endpoint exists.
- AI chat endpoint exists.

### Database / Persistence
- PostgreSQL is used.
- SQLAlchemy models are used.
- There is no Alembic yet.
- Safe MVP schema patches are used with ALTER TABLE ADD COLUMN IF NOT EXISTS.
- Destructive migrations are forbidden.
- Existing data must not be dropped.

## 3. Known Current Gaps

The most important current gaps:

1. Goal conversions are not yet fully loaded from Yandex Metrika by goal ID.
   Current data can still rely on total/general conversions from Yandex Direct.
   This must be fixed.

2. The AI needs stronger server-side context.
   AI should not rely only on frontend-provided client_context.
   It should load trusted backend context:
   - client settings;
   - Yandex binding;
   - sync jobs;
   - performance summary;
   - campaign diagnostics;
   - optimization plan;
   - selected goal IDs;
   - conversion source.

3. AI UI should become one unified AI analyst chat.
   Avoid multiple fragmented AI panels.

4. Optimization actions must remain drafts only.
   No write actions to Yandex Direct until explicit approval workflow exists.

5. Proper migrations with Alembic are needed later.
   For MVP, safe schema patches are acceptable.

## 4. Target Product Vision

The final target product should support the following flow:

1. User logs in by email.
2. User creates a client/project.
3. User enters:
   - Yandex Direct login;
   - Yandex Metrika counter ID;
   - one or multiple Yandex Metrika goal IDs;
   - target CPA;
   - notes/business context.
4. User connects Yandex OAuth.
5. User binds the connected Yandex account to the selected client.
6. User runs sync.
7. Backend loads:
   - Direct campaign cost/impressions/clicks;
   - Metrika goal conversions by selected goal IDs;
   - sync metadata and warnings.
8. Summary shows:
   - total spend;
   - clicks;
   - impressions;
   - CTR;
   - CPC;
   - selected goal conversions;
   - CPA by selected goals;
   - conversion source.
9. Optimization workspace detects:
   - spend without goal conversions;
   - high CPA;
   - low CTR;
   - low data;
   - inefficient spend share;
   - promising campaigns.
10. AI chat can answer questions about:
   - all campaigns;
   - a selected campaign;
   - selected goal IDs;
   - conversion source;
   - optimization plan.
11. AI produces safe draft actions.
12. User reviews/approves actions.
13. Only after explicit approval, future versions may apply write actions to Yandex Direct.

## 5. MVP Roadmap

### Phase 1: Stable User + Client Infrastructure
Status: Mostly done.

Includes:
- email login;
- session auth;
- user/workspace scoping;
- client CRUD;
- per-client Yandex binding;
- app auth gate;
- logout;
- backend API config.

### Phase 2: Data Sync Foundation
Status: Partially done.

Includes:
- Yandex Direct sync;
- sync jobs;
- stored campaign stats;
- performance summary;
- no fake/demo data.

Remaining:
- Yandex Metrika goal conversions by selected goal IDs;
- robust conversion source labeling;
- sync warnings when goal data is unavailable.

### Phase 3: Goal-Based Analytics
Status: In progress / next priority.

Need:
- support one or multiple goal IDs;
- parse goal IDs from client settings;
- load goal conversions from Metrika;
- map Metrika goal data to Direct campaigns safely;
- show goal conversion source in summary;
- compute CPA by selected goals;
- do not allocate goal conversions artificially unless explicitly marked as estimated.

### Phase 4: AI Optimization Workspace
Status: Partially done.

Need:
- stronger server-side AI context;
- unified AI analyst chat;
- campaign selector;
- quick actions;
- optimization plan as draft actions;
- evidence-based AI responses.

### Phase 5: Approval Workflow
Status: Not started.

Need:
- action draft storage;
- user approval;
- status tracking;
- no direct Yandex write actions without approval.

### Phase 6: Safe Yandex Direct Write Actions
Status: Future only.

Potential actions:
- pause keyword/ad/campaign;
- add negative keywords;
- adjust bid/budget;
- create recommendations.

Rules:
- never auto-apply;
- require explicit approval;
- log every action;
- rollback plan required where possible.

## 6. Engineering Rules

### General
- Prefer small, reviewable PRs, but larger cohesive product iterations are acceptable.
- Always run:
  npm run build
  python -m compileall -q backend/app index.py backend/index.py
  python -m pytest -q backend/tests if pytest is available
- If pytest is not installed locally, say so honestly.
- Keep changed files within the allowed scope of the task.
- Do not modify unrelated files.

### Backend
- Use FastAPI.
- Keep auth/organization scoping intact.
- Protected endpoints must require Authorization: Bearer <session_token>.
- Never expose tokens/secrets.
- Never return raw secret values.
- Use current user/organization for client ownership checks.
- Do not create global data leaks between users.
- No destructive migrations.
- Schema patches must use ADD COLUMN IF NOT EXISTS only.
- Prefer clear JSON errors over raw 500.

### Frontend
- Keep static frontend approach.
- Do not introduce React/Vite/build tooling unless explicitly requested.
- Keep app usable on GitHub Pages.
- Preserve backend API URL override.
- Preserve input focus behavior.
- Keep state scoped by user email and selected client.
- Do not leak AI chat or summary between clients.

### AI
- AI must not invent campaign metrics.
- AI must clearly state when goal data is unavailable.
- AI must not claim write actions were applied.
- AI recommendations are draft actions only.
- AI should answer in Russian by default.
- AI context should come from trusted backend data where possible.

### Yandex
- OAuth account is global within user workspace but must be bound to a client.
- Do not use the latest global Yandex token as fallback.
- Sync must use the token bound to the selected client.
- No write actions to Yandex Direct yet.

## 7. Safety Boundaries

Forbidden until explicitly implemented:
- automatic campaign changes;
- automatic bid updates;
- automatic budget changes;
- pausing campaigns/ads/keywords;
- deleting anything from Yandex Direct;
- writing to Yandex Direct without explicit user approval;
- storing plaintext OAuth tokens;
- exposing tokens in logs or API responses;
- showing one user's clients to another user.

## 8. Recommended Next Major Task

Next major task:
Metrika goal sync + unified AI workspace.

This should include:
- conversion_goal_ids field;
- one or multiple goal IDs;
- Yandex Metrika API loader;
- campaign-level goal conversion matching;
- summary conversion-source labeling;
- AI context endpoint/helper;
- unified AI analyst chat;
- quick action prompts;
- campaign context selector;
- per-client AI state.

## 9. Helpful Skills, Subagents, and Tools

The following specialized helpers would improve development speed:

### Backend API specialist
Useful for:
- FastAPI routers;
- auth dependencies;
- API schema design;
- error handling;
- endpoint tests.

### Yandex API specialist
Useful for:
- Yandex Direct Reports API;
- Yandex Metrika API;
- OAuth scopes;
- campaign/goal attribution;
- API pagination and rate limits.

### Data modeling specialist
Useful for:
- SQLAlchemy models;
- sync tables;
- schema patches;
- future Alembic migration plan;
- safe data persistence.

### Frontend static app specialist
Useful for:
- src/main.js refactoring;
- state management without React;
- UI state isolation;
- input/focus safety;
- GitHub Pages constraints.

### AI prompt/context specialist
Useful for:
- server-side AI context builder;
- OpenRouter prompt design;
- anti-hallucination constraints;
- campaign evidence formatting;
- unified AI chat UX.

### QA/test specialist
Useful for:
- regression tests;
- auth-scope tests;
- sync tests;
- AI context tests;
- manual test plans.

### Product manager agent
Useful for:
- MVP scope control;
- prioritization;
- user flow;
- roadmap;
- acceptance criteria.

## 10. Codex Workflow Rules

For every task:
1. Read AGENTS.md.
2. Read PROJECT_PLAN.md.
3. Run git status.
4. Stop if working tree is not clean.
5. Implement only the requested scope.
6. Run required checks.
7. Summarize changed files.
8. Provide manual test steps.
9. Do not claim tests passed if they did not run.
10. Do not make unrelated improvements.

Preferred task flow:
- Create a branch for every major task.
- Keep PRs cohesive.
- Backend + frontend changes are acceptable when needed for one product feature.
- Do not mix product features with formatting-only changes.

## 11. Current Priority Order

1. Metrika goal conversion sync.
2. Unified AI analyst chat.
3. Server-side AI context builder.
4. Improved optimization plan.
5. Approval workflow for draft actions.
6. Safe Yandex Direct write actions after approval.
7. Alembic migrations.
8. Better UI styling and onboarding.
9. Billing/subscriptions later.

## 12. Definition of Done for MVP

MVP is considered usable when:

- user can log in;
- user can create isolated client;
- user can connect Yandex;
- user can bind Yandex account to client;
- user can set Direct login, Metrika counter, goal IDs;
- user can sync real data;
- summary shows cost/click/conversion/CPA by selected goals;
- AI sees campaign-level data;
- AI can answer questions about campaigns;
- AI creates safe optimization plan;
- no data leaks between users/clients;
- no fake/demo campaign data;
- no unsafe write actions.

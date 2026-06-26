# Frontend direction

Decision: do not migrate the MVP frontend yet.

Why: the cabinet still depends on a static frontend that works on GitHub Pages. A full framework migration is useful later, but doing it before the core flow is stable creates too much risk.

Current priority:

1. Keep the static cabinet working.
2. Stabilize client onboarding, account binding, sync, AI analysis, optimization drafts and approval workflow.
3. Add design tokens and reusable UI patterns.
4. Split the large UI file into smaller modules.
5. Migrate to a component framework only after the MVP flow is stable.

Target frontend split:

- core: api, state, storage, router, events, html helpers;
- pages: dashboard, clients, integrations, ai, optimization, journal;
- components: shell, sidebar, app header, panel, button, badge, table, empty state, readiness checklist, sync status, client selector.

Product UX rule: DirectPilot AI is not a generic dashboard. The cabinet should explain what is wrong, why it is wrong, what evidence supports it and what action can safely be approved.

# Frontend architecture

DirectPilot AI frontend is being migrated from a large `src/main.js` file into layered modules.

## Current layers

- `src/app/` — routes, router, page-router, shared app state, hash bridge and client-scoped reset helpers.
- `src/pages/` — page content composers.
- `src/services/` — backend API access.
- `src/stores/` — pure state and data helpers.
- `src/controllers/` — feature orchestration between `main.js`, stores and services.
- `src/components/` — reusable UI primitives.

## Current app helpers

```text
routes.js
router.js
page-router.js
state.js
hash-route-bridge.js
client-scope-reset.js
```

## Current controllers

```text
ai-controller.js
ai-event-bindings.js
clients-controller.js
integrations-controller.js
optimization-controller.js
```

## Current stores

```text
ai-store.js
ai-feature-state.js
business-context-store.js
campaign-store.js
client-store.js
optimization-store.js
```

## Current components scaffold

```text
empty-state.js
panel.js
status-badge.js
index.js
```

These components are intentionally not mass-wired into every page yet. Use them one page at a time where markup duplication is obvious.

## Routing cleanup

`src/app/routes.js` is now the canonical place for route ids, legacy redirects and route mode metadata.

```text
wordstat: legacy
journal: reserved
```

`src/main.js` now imports `normalizeAppRouteId` from `src/app/routes.js`; the old local `primaryAppViews` and `legacyViewRedirects` block has been removed.

The Wordstat and Journal decision is documented in `docs/legacy-pages-decision.md`.

## Auth cleanup

The legacy auth branch in `src/main.js` now persists session data with the same argument order as `src/login.js`:

```text
saveSession(sessionToken, sessionEmail)
```

It accepts both `session_token` and `access_token` backend payload fields as a compatibility fallback.

## Client-scoped reset cleanup

`src/app/client-scope-reset.js` owns the reset patch for state that must be cleared when the selected client changes.

It currently resets:

```text
businessContext
businessContextDraft
clientYandexIntegration
syncJobs
perfSummary
optimizationPlan
optimizationActions
optimizationActionsLoadedFor
optimizationExecutionPreviews
activeView
```

`src/main.js` applies this patch and separately resets AI client-scoped state through `resetAiClientScopedState(aiFeatureState)`.

## Wordstat contract

`docs/wordstat-page-contract.md` defines the target Wordstat feature contract before code migration.

Current status:

```text
wordstat route mode: legacy
current module: src/wordstat.js
current script loading: app.html standalone modules
target module: src/features/wordstat/*
```

Migration must start with store/service extraction, not with moving the full legacy file.

## Page composers

Content composers are wired for Dashboard, Clients, Business Context, Integrations, Optimization and AI Assistant.

Wordstat remains a standalone legacy module until its feature contract is implemented.

Journal remains a reserved route until its product behavior is clear.

## Still in main.js

```text
business context mutable variables and service flows
optimization mutable variables and render callbacks
integrations mutable variables and client list patch callbacks
clients mutable variables and storage/render callbacks
```

## Completed migration sequence

```text
service layer wired
client store wired
ai store wired
campaign store wired
Dashboard content composer wired
Clients content composer wired
Business Context content composer wired
Integrations content composer wired
Optimization content composer wired
AI Assistant content composer wired
AI controller state/context helpers wired
AI controller status/prompt flows wired
AI controller remaining async flows wired
AI event bindings wired
AI feature state facade wired
Business Context store helpers wired
Optimization controller/store wired
Integrations controller wired
Clients controller wired
Router legacy metadata wired
Main route normalization wired
Main auth session persistence fixed
Client scoped reset helper wired
Wordstat page contract documented
Wordstat/Journal decision documented
Components scaffold wired
static validator guards service/store/controller/page wiring
```

## Next safe refactors

```text
1. Define Journal domain model before creating src/pages/journal.js.
2. Use renderPanel/renderEmptyState/renderStatusBadge in one page at a time.
3. Start Wordstat store/service extraction after local validation path is ready.
4. Start new large modules in src/features/* after their contracts are clear.
```

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

Use components one page at a time where markup duplication is obvious.

Current wired pages:

```text
src/pages/integrations.js -> renderPanel, renderEmptyState, renderStatusBadge
src/pages/business-context.js -> renderPanel, renderEmptyState, renderStatusBadge
```

## Feature-first modules

Wordstat has started moving toward the target `src/features/*` structure.

```text
src/features/wordstat/index.js
src/features/wordstat/wordstat-store.js
src/features/wordstat/wordstat-service.js
src/features/wordstat/wordstat-legacy-adapter.js
src/features/wordstat/wordstat-controller.js
src/features/wordstat/wordstat-page.js
src/features/wordstat/wordstat-events.js
```

These files now own pure helpers, API access, a stable legacy facade, async Wordstat flows, reusable render helpers and event handler logic. Legacy `src/wordstat.js` imports the adapter/controller/page/events helpers for feature work, but still owns the outer DOM lifecycle and listener registration.

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
store/service scaffold: created
legacy adapter scaffold: created
controller: created and wired
page renderers: created and wired
events: created and wired
legacy wiring: done
```

Migration started with store/service extraction, a legacy adapter, controller extraction, page-renderer extraction and event-handler extraction, not with moving the full legacy file.

## Journal domain model

`docs/journal-domain-model.md` defines Journal as client-scoped operational history.

Current status:

```text
journal route mode: reserved
current module: none
target module: src/features/journal/*
```

Do not create `src/pages/journal.js` until backend/local source, store, service and page contracts are ready.

## Page composers

Content composers are wired for Dashboard, Clients, Business Context, Integrations, Optimization and AI Assistant.

Wordstat remains a standalone legacy module until module registration replaces the standalone script path.

Journal remains a reserved route until its domain model is implemented.

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
Journal domain model documented
Integrations UI primitives wired
Business Context UI primitives wired
Wordstat store/service scaffold created
Wordstat legacy adapter scaffold created
Wordstat legacy adapter wired
Wordstat controller wired
Wordstat page renderers wired
Wordstat event handlers wired
Wordstat/Journal decision documented
Components scaffold wired
static validator guards service/store/controller/page/events wiring
```

## Next safe refactors

```text
1. Register Wordstat in page renderer after events exist.
2. Remove standalone Wordstat scripts from app.html once feature module fully replaces them.
3. Change Wordstat route mode from legacy to module.
4. Start Journal MVP source/store extraction after backend/local source is chosen.
```

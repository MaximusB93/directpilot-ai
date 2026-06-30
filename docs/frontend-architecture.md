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

Wordstat has moved to module route mode while still keeping a runtime bridge.

```text
src/features/wordstat/index.js
src/features/wordstat/wordstat-store.js
src/features/wordstat/wordstat-service.js
src/features/wordstat/wordstat-legacy-adapter.js
src/features/wordstat/wordstat-controller.js
src/features/wordstat/wordstat-page.js
src/features/wordstat/wordstat-events.js
```

Journal has started its feature-first scaffold with a local MVP source and pure store helpers.

```text
src/features/journal/index.js
src/features/journal/journal-store.js
src/features/journal/journal-local-source.js
```

## Routing cleanup

`src/app/routes.js` is now the canonical place for route ids, legacy redirects and route mode metadata.

```text
wordstat: module
journal: reserved
```

`src/main.js` imports `normalizeAppRouteId` from `src/app/routes.js`; the old local `primaryAppViews` and `legacyViewRedirects` block has been removed.

The Wordstat and Journal decision is documented in `docs/legacy-pages-decision.md`.

## Wordstat contract

Current status:

```text
wordstat route mode: module
runtime import: src/main.js -> import './wordstat.js'
app.html standalone Wordstat scripts: removed
legacy patch modules: imported by src/wordstat.js
target module: src/features/wordstat/*
store/service scaffold: created
legacy adapter scaffold: created
controller: created and wired
page renderers: created and wired
events: created and wired
page registration: created and wired
legacy auto-open bridge: wired
```

`app.html` now loads the app shell plus non-Wordstat app patches. Wordstat runtime is pulled through the app shell.

## Journal domain model

`docs/journal-domain-model.md` defines Journal as client-scoped operational history.

Current status:

```text
journal route mode: reserved
target module: src/features/journal/*
local MVP source: created
store scaffold: created
page/controller/events: pending
```

Do not create `src/pages/journal.js` until page/controller/events exist.

## Page composers

Content composers are wired for Dashboard, Clients, Business Context, Integrations, Optimization, AI Assistant and Wordstat.

Wordstat page module currently provides a bridge shell while `src/wordstat.js` owns the remaining runtime lifecycle.

Journal remains a reserved route until the local source, store, page, controller and events are wired.

## Still in main.js

```text
business context mutable variables and service flows
optimization mutable variables and render callbacks
integrations mutable variables and client list patch callbacks
clients mutable variables and storage/render callbacks
Wordstat runtime import until remaining legacy lifecycle is absorbed by feature modules
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
Wordstat page module registered
Wordstat module route wired in app shell
Wordstat standalone scripts removed from app.html
Wordstat route mode switched to module
Journal local source scaffold created
Journal store scaffold created
Wordstat/Journal decision documented
Components scaffold wired
static validator guards service/store/controller/page/events/page registration/app shell wiring
```

## Next safe refactors

```text
1. Create Journal page/controller around the local source.
2. Create Journal events.
3. Wire Journal into page renderer and client-scope reset.
4. Change Journal route mode from reserved to module.
5. Later: absorb remaining Wordstat runtime bridge and patch modules into feature modules.
```

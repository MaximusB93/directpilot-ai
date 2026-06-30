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

Journal has a feature-first scaffold plus a registered page module.

```text
src/features/journal/index.js
src/features/journal/journal-store.js
src/features/journal/journal-local-source.js
src/features/journal/journal-controller.js
src/features/journal/journal-page.js
src/features/journal/journal-events.js
src/pages/journal.js
```

## Routing cleanup

```text
wordstat: module
journal: reserved
```

`src/app/routes.js` is the canonical place for route ids, legacy redirects and route mode metadata.

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

## Journal domain model

Current status:

```text
journal route mode: reserved
target module: src/features/journal/*
local MVP source: created
store scaffold: created
controller: created
page renderers: created
events: created
page registration: created and wired
app shell runtime: pending
client-scope reset: pending
```

Journal remains a reserved route until app shell runtime and client-scope reset are wired.

## Page composers

Content composers are wired for Dashboard, Clients, Business Context, Integrations, Optimization, AI Assistant, Wordstat and Journal.

Journal page module is registered but not activated as a route yet.

## Still in main.js

```text
business context mutable variables and service flows
optimization mutable variables and render callbacks
integrations mutable variables and client list patch callbacks
clients mutable variables and storage/render callbacks
Wordstat runtime import until remaining legacy lifecycle is absorbed by feature modules
Journal runtime state/source/listeners after the next iteration
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
Journal controller scaffold created
Journal page renderer scaffold created
Journal event handler scaffold created
Journal page module registered
Wordstat/Journal decision documented
Components scaffold wired
static validator guards service/store/controller/page/events/page registration/app shell wiring
```

## Next safe refactors

```text
1. Wire Journal runtime in app shell.
2. Add Journal state to client-scope reset.
3. Change Journal route mode from reserved to module.
4. Later: absorb remaining Wordstat runtime bridge and patch modules into feature modules.
```

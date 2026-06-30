# Frontend architecture

DirectPilot AI frontend is being migrated from a large `src/main.js` file into layered modules.

## Current layers

- `src/app/` — routes, router, page-router, shared app state, hash bridge and client-scoped reset helpers.
- `src/pages/` — page content composers.
- `src/services/` — backend API access.
- `src/stores/` — pure state and data helpers.
- `src/controllers/` — feature orchestration between `main.js`, stores and services.
- `src/components/` — reusable UI primitives.
- `src/features/` — feature-first modules.

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

Journal is now enabled as a module route with local MVP source.

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
journal: module
```

`src/app/routes.js` is the canonical place for route ids, legacy redirects and route mode metadata.

## Journal status

```text
journal route mode: module
local MVP source: created
store scaffold: created
controller: created
page renderers: created
events: created
page registration: created and wired
app shell runtime: wired
client-scope reset: wired
```

## Still in main.js

```text
business context mutable variables and service flows
optimization mutable variables and render callbacks
integrations mutable variables and client list patch callbacks
clients mutable variables and storage/render callbacks
Wordstat runtime import until remaining legacy lifecycle is absorbed by feature modules
Journal runtime state/source/listeners until backend service and app state are extracted further
```

## Completed migration sequence

```text
Wordstat route mode switched to module
Journal local source scaffold created
Journal store scaffold created
Journal controller scaffold created
Journal page renderer scaffold created
Journal event handler scaffold created
Journal page module registered
Journal runtime wired in app shell
Journal client scoped reset wired
Journal route mode switched to module
static validator guards Journal route/runtime/reset wiring
```

## Next safe refactors

```text
1. Add real Journal auto-logging for client/integration/sync/optimization events.
2. Replace Journal local source with backend service once endpoints exist.
3. Later: absorb remaining Wordstat runtime bridge and patch modules into feature modules.
```

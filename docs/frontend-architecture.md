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

Journal is enabled as a module route with local MVP source, auto-logging v1, and details UI.

```text
src/features/journal/index.js
src/features/journal/journal-store.js
src/features/journal/journal-local-source.js
src/features/journal/journal-controller.js
src/features/journal/journal-page.js
src/features/journal/journal-events.js
src/features/journal/journal-logging.js
src/pages/journal.js
```

## Routing cleanup

```text
wordstat: module
journal: module
```

## Journal status

```text
journal route mode: module
local MVP source: created
store scaffold: created
controller: created
page renderers: created
details UI: created
events: created
logging helpers: created
page registration: created and wired
app shell runtime: wired
client-scope reset: wired
Journal auto-logging v1 wired
Journal details UI wired
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
Journal auto-logging v1 wired
Journal details UI wired
static validator guards Journal route/runtime/reset/logging/details wiring
```

## Next safe refactors

```text
1. Add AI recommendation and business-context journal entries.
2. Replace Journal local source with backend service once endpoints exist.
3. Add richer styling for Journal JSON details if needed.
4. Later: absorb remaining Wordstat runtime bridge and patch modules into feature modules.
```

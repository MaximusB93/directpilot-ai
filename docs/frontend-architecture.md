# Frontend architecture

DirectPilot AI frontend is moving from a single large `src/main.js` file to a page-module architecture.

## Current target

Keep one static shell:

- `app.html` — cabinet shell.
- `src/main.js` — temporary bootstrap and legacy renderer.

Move new code toward:

```text
src/app/
  routes.js
  router.js
  state.js

src/pages/
  dashboard.js
  clients.js
  integrations.js
  ai-assistant.js
  wordstat.js
  optimization.js
  journal.js

src/components/
  button.js
  panel.js
  metric-card.js
  status-badge.js
  empty-state.js
  client-selector.js
```

## Routing

The cabinet should use hash routes during the MVP stage:

```text
app.html#dashboard
app.html#clients
app.html#integrations
app.html#ai
app.html#wordstat
app.html#optimization
app.html#journal
```

This keeps the app static-hosting friendly and makes page state shareable/reload-safe.

## Route modules

- `src/app/routes.js` stores route metadata and normalization helpers.
- `src/app/router.js` owns hash navigation helpers.
- `src/app/state.js` stores shared app state and dispatches typed browser events.

## Migration rule

Do not rewrite `src/main.js` in one large commit.

Preferred sequence:

1. Add router/state foundation.
2. Extract dashboard page.
3. Extract clients page.
4. Extract integrations page.
5. Extract AI assistant page.
6. Extract Wordstat last, because it is the most sensitive and stateful area.

## What not to do

- Do not create separate HTML files for every cabinet tab.
- Do not add React/Vite until the static MVP structure is stable.
- Do not add new CSS hotfix files for routine styling; move new reusable styles into a planned `src/styles/` structure.
- Do not mix API calls, render functions, localStorage and event listeners inside the same new module unless it is temporary legacy code.

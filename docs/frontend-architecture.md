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
  page-router.js
  state.js
  hash-route-bridge.js

src/pages/
  index.js
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
- `src/app/page-router.js` connects normalized route ids with registered page modules, contracts, renderer adapters and content composers.
- `src/app/state.js` stores shared app state and dispatches typed browser events.
- `src/app/hash-route-bridge.js` temporarily synchronizes hash routes with legacy `?view=` routing in `src/main.js`.

The bridge marks route resolution on `document.body`:

```text
data-route-id="dashboard"
data-route-mode="module|legacy"
data-page-module="dashboard"
```

This is a temporary debugging and migration aid while `src/main.js` still owns most renderers.

## Page modules

- `src/pages/index.js` is the registry for page metadata, page contracts, renderer adapters and content composers.
- `src/pages/dashboard.js` exposes `renderDashboardPage({ legacyRenderDashboard })` and `renderDashboardContent(context)`.

The dashboard legacy markup still partly lives in `src/main.js`, but the page module now owns the dashboard content composition and these pure HTML builder slices:

```text
renderDashboardIntro
renderDashboardNextStepPanel
renderDashboardEmptyClientPanel
renderDashboardConnectedPanels
renderDashboardContent
```

`renderDashboardContent(context)` is intentionally dependency-injected: it receives legacy panel renderers from `src/main.js` until those panels are extracted one by one.

The contract records:

- route id;
- required page context;
- current legacy renderer;
- extraction status;
- extracted builders;
- next migration step.

This lets new page modules appear before we move the heavy render functions, instead of ripping apart the legacy file in one heroic mistake.

## Migration rule

Do not rewrite `src/main.js` in one large commit.

Preferred sequence:

1. Add router/state foundation.
2. Add hash route bridge.
3. Add dashboard page contract.
4. Add pages registry.
5. Connect pages registry to the app routing layer.
6. Add dashboard renderer adapter.
7. Wire `src/main.js` dashboard route to `renderDashboardPage`.
8. Extract dashboard intro and next-step builders.
9. Add dashboard content composer.
10. Wire `src/main.js` `renderDashboard` to `renderDashboardContent` in one controlled patch.
11. Move the remaining dashboard panels behind the page module in smaller slices.
12. Extract clients page.
13. Extract integrations page.
14. Extract AI assistant page.
15. Extract Wordstat last, because it is the most sensitive and stateful area.

## What not to do

- Do not create separate HTML files for every cabinet tab.
- Do not add React/Vite until the static MVP structure is stable.
- Do not add new CSS hotfix files for routine styling; move new reusable styles into a planned `src/styles/` structure.
- Do not mix API calls, render functions, localStorage and event listeners inside the same new module unless it is temporary legacy code.

# Frontend architecture

DirectPilot AI frontend is moving from a single large `src/main.js` file to a page-module architecture.

## Current target

Keep one static shell:

- `app.html` — cabinet shell.
- `src/main.js` — temporary bootstrap, legacy renderer and event orchestrator.

Move new code toward layered modules:

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
  business-context.js
  ai-assistant.js
  optimization.js
  wordstat.js
  journal.js

src/services/
  index.js
  clients-service.js
  integrations-service.js
  business-context-service.js
  sync-service.js
  performance-service.js
  optimization-service.js
  ai-service.js

src/stores/
  index.js
  client-store.js
  ai-store.js

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
app.html#business-context
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

`src/pages/index.js` is the registry for page metadata, page contracts, renderer adapters and content composers.

Registered page contracts now exist for:

```text
dashboard
clients
business-context
integrations
ai
optimization
```

`src/pages/dashboard.js` exposes `renderDashboardPage({ legacyRenderDashboard })` and `renderDashboardContent(context)`.

The dashboard legacy markup still partly lives in `src/main.js`, but the page module now owns the dashboard content composition and these pure HTML builder slices:

```text
renderDashboardIntro
renderDashboardNextStepPanel
renderDashboardEmptyClientPanel
renderDashboardConnectedPanels
renderDashboardContent
```

`renderDashboardContent(context)` is intentionally dependency-injected: it receives legacy panel renderers from `src/main.js` until those panels are extracted one by one.

`src/pages/clients.js` now exposes `renderClientsContent(context)` and these pure HTML builder slices:

```text
renderClientsIntro
renderClientCreatePanel
renderClientSettingsPanel
renderClientGrid
renderClientsContent
```

The clients page content composer is registered in `PAGE_CONTENT_RENDERERS`, but `src/main.js` still needs one controlled patch to route `renderClients()` through it.

Other page modules are currently contract-only. They document required context and legacy renderer names before we move their markup.

## Service layer

Service modules isolate backend calls that previously lived inside `src/main.js`:

```text
clients-service.js            /clients CRUD
integrations-service.js       Yandex OAuth and client binding
business-context-service.js   business context and memory notes
sync-service.js               sync run and sync job history
performance-service.js        performance summary
optimization-service.js       optimization plan/actions/execution preview
ai-service.js                 OpenRouter status, generation, chat, recommendations, prompt debug
```

`src/main.js` now uses these service modules instead of direct inline `apiFetch(...)` calls. The static validator checks this with `main no inline apiFetch calls`, so direct backend access should stay in `src/services/` or dedicated feature modules.

## Store layer

Store scaffolds now exist for:

```text
client-store.js   selected client id, selected client resolution, localStorage key helpers
ai-store.js       initial AI chat/model state constants
```

They are intentionally small until `main.js` stops owning all mutable state.

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
10. Add contract-only page modules for clients, integrations, business context, AI assistant and optimization.
11. Add service and store scaffolds.
12. Wire `src/main.js` `renderDashboard` to `renderDashboardContent` in one controlled patch.
13. Replace inline API functions in `src/main.js` with service imports.
14. Update static validation to guard service-layer wiring.
15. Add clients page content composer.
16. Wire `src/main.js` `renderClients` to `renderClientsContent` in one controlled patch.
17. Move remaining dashboard panels behind the page module in smaller slices.
18. Extract integrations page.
19. Extract business context page.
20. Extract AI assistant page.
21. Extract optimization page.
22. Extract Wordstat last, because it is the most sensitive and stateful area.

## What not to do

- Do not create separate HTML files for every cabinet tab.
- Do not add React/Vite until the static MVP structure is stable.
- Do not add new CSS hotfix files for routine styling; move new reusable styles into a planned `src/styles/` structure.
- Do not mix API calls, render functions, localStorage and event listeners inside the same new module unless it is temporary legacy code.

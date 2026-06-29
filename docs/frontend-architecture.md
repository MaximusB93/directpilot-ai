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
  campaign-store.js

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

This is a temporary debugging and migration aid while `src/main.js` still owns app orchestration.

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

The clients page content composer is registered in `PAGE_CONTENT_RENDERERS`, and `src/main.js` now routes `renderClients()` through `renderClientsContent(context)`.

`src/pages/business-context.js` now exposes `renderBusinessContextContent(context)` and these pure HTML builder slices:

```text
renderBusinessContextIntro
renderBusinessContextPanel
renderBusinessContextContent
```

The business context content composer is registered in `PAGE_CONTENT_RENDERERS`, and `src/main.js` now routes `renderBusinessContext()` through `renderBusinessContextContent(context)`. The dashboard still uses `renderBusinessContextPanel(compact)` as an injected legacy-compatible panel wrapper.

`src/pages/integrations.js` now exposes `renderIntegrationsContent(context)` and these pure HTML builder slices:

```text
renderIntegrationsIntro
renderYandexConnectPanel
renderClientYandexAccountPanel
renderIntegrationsContent
```

The integrations content composer is registered in `PAGE_CONTENT_RENDERERS`, and `src/main.js` now routes `renderIntegrations()` through `renderIntegrationsContent(context)`. The event handlers still live in `src/main.js`, so existing `data-integration`, `data-refresh-client-yandex`, `data-bind-yandex-account` and `data-unbind-yandex` actions keep working.

`src/pages/optimization.js` now exposes `renderOptimizationContent(context)` and these pure HTML builder slices:

```text
renderOptimizationIntro
renderOptimizationPlanPanel
renderOptimizationActionsPanel
renderOptimizationContent
```

The optimization content composer is registered in `PAGE_CONTENT_RENDERERS`, and `src/main.js` now routes `renderOptimization()` through `renderOptimizationContent(context)`. The event handlers still live in `src/main.js`, so existing `data-load-optimization-plan`, `data-load-optimization-actions`, `data-create-optimization-drafts`, `data-update-optimization-action` and `data-preview-optimization-action` actions keep working.

`src/pages/ai-assistant.js` now exposes `renderAiAssistantContent(context)` and these pure HTML builder slices:

```text
renderAiAssistantIntro
renderAiStatusPanel
renderAiPromptDebugPanel
renderAiChat
renderClientAiRecommendations
renderAiQuickActions
renderAiAssistantContent
```

The AI assistant content composer is registered in `PAGE_CONTENT_RENDERERS`, and `src/main.js` now routes `renderAiAssistant()` through `renderAiAssistantContent(context)`. The event handlers still live in `src/main.js`, so existing model settings, prompt debug, chat, sample prompts, client recommendations and quick prompt actions keep working.

Current contract-only modules:

```text
none
```

All core page content composers are now wired. The next work is no longer page markup extraction, but state and event-handler extraction.

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
client-store.js     selected client id, selected client resolution, localStorage key helpers
ai-store.js         initial AI chat/model/generation state, AI budget helpers, chat payload builders
campaign-store.js   campaign names, campaign ids, performance summary campaign options and filtering helpers
```

They are intentionally small until `main.js` stops owning all mutable state.

Current wiring:

```text
client-store.js     wired into selected client loading/saving and client normalization
ai-store.js         wired into initial AI state, AI helper delegation, chat payloads and AI status normalization
campaign-store.js   wired into `campaignOptions()` through `campaignsStore.getCampaignOptions(perfSummary)`
```

## Static validation

`scripts/validate-static.mjs` protects the migration from quiet regressions.

Important checks:

```text
main no inline apiFetch calls
main no duplicated async
main ai store import
main ai store initial state wiring
main ai store helper delegation
main ai chat store delegation
main clients content wiring
main campaign store wiring
main business context content wiring
main integrations content wiring
main ai assistant content wiring
main optimization content wiring
business context content composer
business context content registry
integrations content composer
integrations content registry
ai assistant content composer
ai assistant content registry
optimization content composer
optimization content registry
```

When a new extraction is wired, add a static check in the same or next commit. The validator is intentionally simple string matching. Primitive, yes. Effective enough to keep accidental regressions from crawling into production like raccoons in a ventilation shaft.

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
14. Wire `client-store.js`, `ai-store.js` and `campaign-store.js` into `src/main.js` in small controlled patches.
15. Wire `renderClients()` to `renderClientsContent(context)`.
16. Add validator checks after each migration step.
17. Move `business-context` page markup into its page content composer.
18. Move `integrations` page markup into its page content composer.
19. Move `optimization` page markup into its page content composer.
20. Move `ai` page markup into its page content composer.

## Current progress snapshot

Completed:

```text
service layer wired
client store wired
ai store wired
campaign store scaffolded and wired
Dashboard content composer wired
Clients content composer wired
Business Context content composer wired
Integrations content composer wired
Optimization content composer wired
AI Assistant content composer wired
static validator guards service/store/page wiring
```

Next iteration:

```text
Split AI state/event handlers from `src/main.js` into dedicated AI store/controller modules.
```

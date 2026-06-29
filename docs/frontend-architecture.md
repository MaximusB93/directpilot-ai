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

src/controllers/
  ai-controller.js
  ai-event-bindings.js

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
  ai-feature-state.js
  business-context-store.js
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

Core page content composers are wired for:

```text
Dashboard
Clients
Business Context
Integrations
Optimization
AI Assistant
```

`src/pages/ai-assistant.js` owns AI assistant markup composition. Model settings, prompt debug, chat, sample prompts, client recommendations and quick prompt actions route through `src/controllers/ai-event-bindings.js`, while state mutation happens through the `aiFeatureState` facade in `src/main.js`.

`src/pages/business-context.js` owns Business Context markup composition. Business Context model helpers now live in `src/stores/business-context-store.js`, while `src/main.js` keeps thin wrappers where current client/state access is still needed.

Current contract-only modules:

```text
none
```

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
client-store.js             selected client id, selected client resolution, localStorage key helpers
ai-store.js                 initial AI chat/model/generation state, AI budget helpers, chat payload builders
ai-feature-state.js         AI feature state facade split into model/generation/chat sections
business-context-store.js   Business Context normalization, backend payload, form draft, copy text, AI payload and completeness helpers
campaign-store.js           campaign names, campaign ids, performance summary campaign options and filtering helpers
```

Current wiring:

```text
client-store.js             wired into selected client loading/saving and client normalization
ai-store.js                 wired into AI helpers, chat payloads, status normalization and ai-feature-state initial values
ai-feature-state.js         wired into `src/main.js` as `aiFeatureState.model`, `aiFeatureState.generation` and `aiFeatureState.chat`
business-context-store.js   wired into `src/main.js` wrappers: normalizeBusinessContext, businessContextPayload, defaultBusinessContext, hasBusinessContextData, businessContextCopyText, setBusinessContextDraftFromForm, businessContextForAi and contextCompletenessScore
campaign-store.js           wired into `campaignOptions()` through `campaignsStore.getCampaignOptions(perfSummary)`
```

## Controller layer

Controllers are the migration layer between `src/main.js`, stores and services.

Current controller modules:

```text
ai-controller.js        AI state snapshots, AI page context assembly, thin delegates to AI store request builders, and AI async flows
ai-event-bindings.js   AI submit/input/change/click event routing for model settings, prompt debug, chat, recommendations and quick prompts
```

Current AI controller wiring:

```text
currentAiModelState() delegates to createAiModelStateSnapshot(...) with aiFeatureState.model
currentAiChatState() delegates to createAiChatStateSnapshot(...) with aiFeatureState.chat
activeAiModel()/activeAiBudget() delegate through ai-controller.js
aiChatRequestPayload()/aiPromptDebugParams() delegate through ai-controller.js
aiAssistantPageContext() delegates to createAiAssistantPageContext(...) with aiFeatureState fields
loadAiStatus() delegates to loadAiStatusFlow(...) and writes aiFeatureState.model.status
loadAiPromptDebug() delegates to loadAiPromptDebugFlow(...) and writes aiFeatureState.generation
requestAiRecommendations() delegates to requestAiRecommendationsFlow(...) and writes aiFeatureState.generation
sendAiChatMessage() delegates to sendAiChatMessageFlow(...) and writes aiFeatureState.chat
saveAiMemoryNote() delegates to saveAiMemoryNoteFlow(...) and writes aiFeatureState.generation.memoryStatus
generateAiInsight() delegates to generateAiInsightFlow(...) and writes aiFeatureState.generation
AI input/change/submit/click event branches delegate to ai-event-bindings.js
```

Still in `src/main.js` after this controller/store step:

```text
callback wiring for AI bindings and flows
business context mutable variables and service flows
optimization mutable variables and service flows
integrations mutable variables and service flows
clients mutable variables and service flows
```

## Static validation

`scripts/validate-static.mjs` protects the migration from quiet regressions.

Important checks include:

```text
main no inline apiFetch calls
main no duplicated async
main ai feature state wiring
main no legacy ai globals
main business context store import
main business context store delegation
main business context wrappers kept
main ai controller flow delegation
main ai event bindings delegation
main business context content wiring
business context store helpers
business context store field mapping
Business Context store helpers wired
```

When a new extraction is wired, add a static check in the same or next commit. The validator is intentionally simple string matching. Primitive, yes. Effective enough to keep accidental regressions from crawling into production like raccoons in a ventilation shaft.

## Migration rule

Do not rewrite `src/main.js` in one large commit.

Completed migration sequence so far:

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
AI controller state/context helpers wired
AI controller status/prompt flows wired
AI controller remaining async flows wired
AI event bindings wired
AI feature state facade wired
Business Context store helpers wired
static validator guards service/store/controller/page wiring
```

Next iteration:

```text
Move Optimization controller/store helpers out of `src/main.js`: normalizeOptimizationPlan, normalizeOptimizationAction, normalizeOptimizationPreview, filtered actions and optimization async flow orchestration.
```

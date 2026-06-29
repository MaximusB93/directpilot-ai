# Frontend architecture

DirectPilot AI frontend is being migrated from a large `src/main.js` file into layered modules.

## Target layers

```text
src/app/          routes, router, page-router, shared app state and hash bridge
src/pages/        page content composers
src/services/     backend API access
src/stores/       pure state/data helpers
src/controllers/  feature orchestration between main, stores and services
src/components/   reusable UI components, still mostly future work
```

## Current modules

```text
src/controllers/
  ai-controller.js
  ai-event-bindings.js
  clients-controller.js
  integrations-controller.js
  optimization-controller.js

src/stores/
  ai-store.js
  ai-feature-state.js
  business-context-store.js
  campaign-store.js
  client-store.js
  optimization-store.js
```

## Page composers

Content composers are wired for:

```text
Dashboard
Clients
Business Context
Integrations
Optimization
AI Assistant
```

`src/pages/clients.js` owns Clients markup composition. Client loading, creation, settings and deletion orchestration now routes through `src/controllers/clients-controller.js`, while `src/main.js` still owns selected-client mutable state, storage callbacks and cross-feature reset side effects.

`src/pages/integrations.js` owns Integrations markup composition. Yandex OAuth/status/client-binding orchestration routes through `src/controllers/integrations-controller.js`, while `src/main.js` still owns mutable state, client list patches and render callbacks.

`src/pages/optimization.js` owns Optimization markup composition. Normalization/filtering helpers live in `src/stores/optimization-store.js`, and async orchestration routes through `src/controllers/optimization-controller.js`.

`src/pages/business-context.js` owns Business Context markup composition. Business Context model helpers live in `src/stores/business-context-store.js`.

`src/pages/ai-assistant.js` owns AI Assistant markup composition. AI state uses `aiFeatureState`, AI flows route through `src/controllers/ai-controller.js`, and AI event branches route through `src/controllers/ai-event-bindings.js`.

## Controller wiring

```text
AI input/change/submit/click event branches delegate to ai-event-bindings.js
AI async flows delegate to ai-controller.js
Client backend loading delegates to loadClientsFromApiFlow(...)
Client creation delegates to createClientFlow(...)
Client settings draft delegates to createClientSettingsDraftFromForm(...)
Client settings save delegates to saveClientSettingsFlow(...)
Client deletion delegates to deleteClientFlow(...)
Optimization async flows delegate to optimization-controller.js
Yandex OAuth/status/bind/unbind flows delegate to integrations-controller.js
```

## Still in main.js

```text
selected client side-effect reset block
business context mutable variables and service flows
optimization mutable variables and render callbacks
integrations mutable variables and client list patch callbacks
clients mutable variables and storage/render callbacks
legacy routing glue
```

## Static validation

`scripts/validate-static.mjs` guards the migration with string-based checks. Important checks now include:

```text
main no inline apiFetch calls
main ai feature state wiring
main business context store delegation
main optimization controller delegation
main integrations controller delegation
main clients controller import
main clients controller delegation
clients controller flows
clients controller services
Clients controller wired
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
static validator guards service/store/controller/page wiring
```

## Next iteration

```text
Router cleanup + Wordstat/Journal decision + components старт: reduce remaining routing glue, decide what stays legacy, and start extracting reusable UI components only where it is safe.
```

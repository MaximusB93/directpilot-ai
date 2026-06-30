# Wordstat page contract

## Status

Wordstat is registered in the app page registry and opened through the app shell. `app.html` no longer loads Wordstat as separate standalone scripts.

Target feature-first module:

```text
src/features/wordstat/
  index.js
  wordstat-page.js
  wordstat-controller.js
  wordstat-store.js
  wordstat-service.js
  wordstat-legacy-adapter.js
  wordstat-events.js
```

Current extraction status:

```text
wordstat-store.js: created
wordstat-service.js: created
wordstat-legacy-adapter.js: created
wordstat-controller.js: created and wired
wordstat-page.js: created and wired
wordstat-events.js: created and wired
src/pages/wordstat.js: created and registered
legacy src/wordstat.js wiring: done with module auto-open bridge
app.html standalone Wordstat scripts: removed
route mode: legacy, pending module switch
```

## Current entrypoints

`app.html` loads only the app shell and non-Wordstat app patches:

```text
src/app/hash-route-bridge.js
src/main.js
src/business_context_autofill.js
src/performance_range_panel.js
```

`src/main.js` imports Wordstat runtime:

```js
import './wordstat.js';
```

`src/wordstat.js` temporarily imports legacy Wordstat patch modules while the feature still owns the runtime bridge:

```js
import './wordstat_date_fix.js';
import './wordstat_regions_patch.js';
import './wordstat_ai_chat.js';
import './wordstat_chart_hover.js';
```

`src/pages/wordstat.js` is registered in `src/pages/index.js` and renders a module shell with `.workspace` for the current Wordstat renderer.

`src/main.js` owns the Wordstat route entry in the sidebar and render map through `renderWordstat()`.

`src/wordstat.js` still owns the outer `renderWordstatPage()` orchestrator, navigation injection, chart tooltip DOM helpers and document listener registration.

## Extracted responsibilities

### Store

```text
src/features/wordstat/wordstat-store.js
```

Owns pure form/date/request/summary helpers:

```text
createDefaultWordstatForm()
createInitialWordstatState()
parseWordstatPhrases(value)
parseWordstatCustomRegions(value)
createSelectedWordstatRegionIds(form)
createWordstatRequestBody(form, clientId, overrides)
createPreviousWordstatPeriodRange(form)
buildWordstatTotalPoints(result)
buildWordstatTotalSummary(result)
calculateWordstatPercentDelta(current, previous)
regionsSummary(regionIds, regionById)
```

Store must not call API, read/write DOM, attach listeners, render UI or read localStorage directly.

### Service

```text
src/features/wordstat/wordstat-service.js
```

Owns backend calls:

```text
fetchWordstatConnection()
fetchWordstatDynamics(requestBody)
```

Backend contract:

```text
GET /wordstat/connection
POST /wordstat/dynamics/batch
```

### Legacy adapter

```text
src/features/wordstat/wordstat-legacy-adapter.js
```

Provides the stable facade used by `src/wordstat.js` while the old runtime still exists.

### Controller

```text
src/features/wordstat/wordstat-controller.js
```

Owns async flows:

```text
openWordstatFlow(...)
submitWordstatDynamicsFlow(...)
compareWordstatPeriodFlow(...)
copyWordstatJsonFlow(...)
```

Controller receives dependencies explicitly and must not own DOM selectors.

### Page renderers

```text
src/features/wordstat/wordstat-page.js
```

Owns reusable HTML render helpers through:

```text
createWordstatPageRenderers(context)
```

Page functions must receive context and return HTML strings. They must not call API or attach listeners.

### Events

```text
src/features/wordstat/wordstat-events.js
```

Owns event handler logic through:

```text
createWordstatEventHandlers(context)
```

Events functions receive context and event objects. They must not register document listeners themselves.

### App page registration

```text
src/pages/wordstat.js
```

Owns:

```text
WORDSTAT_PAGE_ID
wordstatPage
wordstatPageContract()
renderWordstatContent(context)
```

Current `renderWordstatContent(context)` provides a bridge shell, not the final full Wordstat page. It must keep a `.workspace` element while the legacy runtime exists.

## Routing contract

Current route mode:

```text
wordstat: legacy
```

Target route mode after the next migration:

```text
wordstat: module
```

Migration condition before changing route mode:

```text
1. `src/features/wordstat/wordstat-page.js` exists. Done.
2. `src/features/wordstat/wordstat-service.js` owns backend calls. Done.
3. `src/features/wordstat/wordstat-store.js` owns request/state helpers. Done.
4. `src/features/wordstat/wordstat-controller.js` owns async flows. Done.
5. `src/features/wordstat/wordstat-events.js` owns event handlers. Done.
6. `PAGE_CONTENT_RENDERERS` can render Wordstat from context. Done.
7. `app.html` no longer loads standalone Wordstat scripts. Done.
8. Route mode can be changed from legacy to module. Pending.
```

## Migration order

```text
1. Move pure form/date/request helpers into wordstat-store.js. Done.
2. Move GET /wordstat/connection and POST /wordstat/dynamics/batch into wordstat-service.js. Done.
3. Create legacy adapter facade. Done.
4. Wire legacy src/wordstat.js to use wordstat-legacy-adapter.js. Done.
5. Move async open/submit/compare/copy flows into wordstat-controller.js. Done.
6. Move render helpers into wordstat-page.js. Done.
7. Move input/change/click/submit listeners into wordstat-events.js. Done.
8. Register Wordstat in page renderer. Done.
9. Remove standalone Wordstat scripts from app.html. Done.
10. Change route mode from legacy to module.
```

## Known risks

```text
region tree is large and should not be edited manually without validation
current Wordstat script still registers document listeners from legacy shell
legacy patch modules are still imported by src/wordstat.js
clipboard and tooltip behavior must stay outside pure page/store code
comparison uses the same backend endpoint as current dynamics
selected client currently comes from DOM/localStorage fallback and must become explicit context
```

## Do not do yet

```text
Do not move the full legacy file into src/features/wordstat as-is.
Do not delete legacy Wordstat patch modules until their behavior is absorbed into feature modules.
Do not edit region arrays by hand unless the change is isolated and validated.
```

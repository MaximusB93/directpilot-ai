# Wordstat page contract

## Status

`src/wordstat.js` remains a legacy standalone module, but it now uses the Wordstat feature store/service/controller/page helpers through the legacy adapter and feature renderers.

The target direction is a feature-first module:

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
wordstat-events.js: pending
legacy src/wordstat.js wiring: done
```

Do not move the current module as one large file. First split service, store, controller, page and events contracts.

## Current legacy entrypoints

`app.html` currently loads Wordstat as separate ES modules:

```text
src/wordstat.js
src/wordstat_date_fix.js
src/wordstat_regions_patch.js
src/wordstat_ai_chat.js
src/wordstat_chart_hover.js
```

`src/wordstat.js` still owns the outer `renderWordstatPage()` orchestrator, navigation injection, chart tooltip behavior and submit/click/input/change listeners.

`src/wordstat.js` no longer calls `apiFetch` directly. Backend calls are delegated through `src/features/wordstat/wordstat-service.js` via `src/features/wordstat/wordstat-legacy-adapter.js`.

`src/wordstat.js` no longer owns async Wordstat flows directly. It calls `src/features/wordstat/wordstat-controller.js` wrappers for open, submit, compare and copy JSON flows.

`src/wordstat.js` no longer owns most reusable Wordstat render helpers directly. It creates render helpers through `src/features/wordstat/wordstat-page.js` and keeps only the outer legacy DOM shell.

## Existing shared dependencies

`src/wordstat.js` imports shared helpers:

```text
src/core/format.js     formatNumber, formatPercent
src/core/html.js       escapeHtml
src/core/storage.js    getCurrentEmail, scopedStorageKey
```

Feature helpers are imported through:

```text
src/features/wordstat/wordstat-legacy-adapter.js
src/features/wordstat/wordstat-controller.js
src/features/wordstat/wordstat-page.js
```

Keep shared dependencies. Do not duplicate local API, HTML escaping or format helpers.

## Backend API contract

### Check connection

```text
GET /wordstat/connection
```

Expected UI use:

```text
connection.configured
connection.can_call_api
connection.provider
connection.message
```

### Load dynamics

```text
POST /wordstat/dynamics/batch
```

Request body:

```json
{
  "phrases": ["купить диван", "диван кровать"],
  "period": "WEEKLY",
  "fromDate": "2026-03-30",
  "toDate": "2026-06-30",
  "regions": ["213"],
  "devices": ["DEVICE_ALL"],
  "clientId": "client-id-or-null",
  "forceRefresh": false
}
```

`period` allowed values:

```text
DAILY
WEEKLY
MONTHLY
```

`devices` current values:

```text
DEVICE_ALL
DEVICE_DESKTOP
DEVICE_PHONE
DEVICE_TABLET
```

The same endpoint is used for comparison requests by changing `fromDate`, `toDate` and forcing `forceRefresh: false`.

## Store contract

Target file:

```text
src/features/wordstat/wordstat-store.js
```

Current status:

```text
created and used by legacy src/wordstat.js through wordstat-legacy-adapter.js
```

Responsibilities:

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

Store must not:

```text
call apiFetch
read DOM
write DOM
attach event listeners
call render
read localStorage directly
```

## Service contract

Target file:

```text
src/features/wordstat/wordstat-service.js
```

Current status:

```text
created and used by legacy src/wordstat.js through wordstat-legacy-adapter.js
```

Responsibilities:

```text
fetchWordstatConnection()
fetchWordstatDynamics(requestBody)
```

Service must only call backend and parse/validate the response enough to throw useful errors.

Service must not:

```text
mutate wordstat state
render UI
read form elements
read selected client from DOM
```

## Legacy adapter contract

Target file:

```text
src/features/wordstat/wordstat-legacy-adapter.js
```

Current status:

```text
created and imported by src/wordstat.js
```

Responsibilities:

```text
createWordstatLegacyApi({ state, getSelectedClientId, regionById, service })
export store helpers
export service helpers
provide a stable facade for legacy src/wordstat.js wiring
```

The adapter exists to avoid importing many feature helpers directly inside the legacy file. Legacy wiring now imports this facade and delegates store/service work through it.

## Controller contract

Target file:

```text
src/features/wordstat/wordstat-controller.js
```

Current status:

```text
created and used by legacy src/wordstat.js
```

Responsibilities:

```text
openWordstatFlow(...)
submitWordstatDynamicsFlow(...)
compareWordstatPeriodFlow(...)
copyWordstatJsonFlow(...)
```

Controller receives dependencies explicitly:

```text
state
syncFormState
parsePhrases
loadConnection
loadDynamics
ensureNav
render
copyText
```

Controller may orchestrate async work but must not own DOM selectors.

## Page contract

Target file:

```text
src/features/wordstat/wordstat-page.js
```

Current status:

```text
created and used by legacy src/wordstat.js through createWordstatPageRenderers()
```

Responsibilities:

```text
createWordstatPageRenderers(context)
renderCompareControls()
renderWordstatLimitsPanel(phrasesCount, regionsCount)
renderQuotaWarnings()
renderRegionModal()
renderRegionTreeNode(node, level)
renderWordstatEmptyState()
renderWordstatResult(result)
renderPhraseSummaryTable(result)
renderWordstatChart(result, comparison)
renderComparisonPanel(current, previous)
renderComparisonTotalRow(current, previous)
renderTotalSeries(result)
renderWordstatSeries(series)
renderSeriesTable(series)
```

Page functions must receive context and return HTML strings. They must not call API or attach listeners.

## Events contract

Target file:

```text
src/features/wordstat/wordstat-events.js
```

Responsibilities:

```text
handleWordstatInputEvent(event, context)
handleWordstatChangeEvent(event, context)
handleWordstatClickEvent(event, context)
handleWordstatSubmitEvent(event, context)
handleWordstatTooltipEvent(event, context)
```

Events should be wired from the app shell or a feature mount function after the feature page exists.

## Routing contract

Current route mode:

```text
wordstat: legacy
```

Target route mode after migration:

```text
wordstat: module
```

Migration condition before changing route mode:

```text
1. `src/features/wordstat/wordstat-page.js` exists.
2. `src/features/wordstat/wordstat-service.js` owns backend calls.
3. `src/features/wordstat/wordstat-store.js` owns request/state helpers.
4. `src/features/wordstat/wordstat-controller.js` owns async flows.
5. `src/features/wordstat/wordstat-events.js` owns event handlers.
6. `PAGE_CONTENT_RENDERERS` can render Wordstat from context.
7. `app.html` no longer needs standalone Wordstat scripts.
```

## Migration order

```text
1. Move pure form/date/request helpers into wordstat-store.js. Done: scaffold created.
2. Move GET /wordstat/connection and POST /wordstat/dynamics/batch into wordstat-service.js. Done: scaffold created.
3. Create legacy adapter facade. Done: scaffold created.
4. Wire legacy src/wordstat.js to use wordstat-legacy-adapter.js. Done.
5. Move async open/submit/compare/copy flows into wordstat-controller.js. Done.
6. Move render helpers into wordstat-page.js. Done.
7. Move input/change/click/submit listeners into wordstat-events.js.
8. Register Wordstat in page renderer.
9. Remove standalone Wordstat scripts from app.html.
10. Change route mode from legacy to module.
```

## Known risks

```text
region tree is large and should not be edited manually without validation
current Wordstat scripts still mutate DOM outside page-router
standalone scripts can conflict with main render lifecycle
clipboard and tooltip behavior must stay outside pure page/store code
comparison uses the same backend endpoint as current dynamics
selected client currently comes from DOM/localStorage fallback and must become explicit context
```

## Do not do yet

```text
Do not move the full legacy file into src/features/wordstat as-is.
Do not wire Wordstat into PAGE_CONTENT_RENDERERS before events exist.
Do not remove app.html Wordstat scripts until the feature module fully replaces them.
Do not edit region arrays by hand unless the change is isolated and validated.
```

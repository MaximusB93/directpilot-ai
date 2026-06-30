# Journal domain model

## Status

Journal MVP is registered, wired in the app shell, enabled as a module route, has auto-logging v1, and renders entry details.

Current route metadata:

```text
Route id: journal
Route mode: module
Feature scaffold: src/features/journal/*
Page module: src/pages/journal.js
Runtime: src/main.js
Source: local MVP source
```

Current extraction status:

```text
journal-store.js: created
journal-local-source.js: created
journal-controller.js: created
journal-page.js: created
journal-events.js: created
journal-logging.js: created
src/pages/journal.js: created and registered
app shell runtime wiring: done
client-scope reset: done
route mode switch: done
auto-logging v1: done
details UI: done
journal-service.js: pending backend endpoints
```

## Auto-logging v1

Wired events:

```text
client.selected
client.created
client.updated
optimization.action_status_changed
sync.started
sync.failed
sync.<backend status>
integration.yandex_account_bound
integration.yandex_account_unbound
```

## Entry details UI

Journal entries render a native expandable details panel.

Rendered details:

```text
before
after
metadata
```

If an entry has no useful details, the UI shows a small empty details state instead of an empty JSON block.

## Current module contracts

### Store

```text
src/features/journal/journal-store.js
```

Owns normalization, filters, grouping and entry payload helpers.

### Local MVP source

```text
src/features/journal/journal-local-source.js
```

Owns scoped local storage source methods.

### Controller

```text
src/features/journal/journal-controller.js
```

Owns async flows:

```text
loadJournalEntriesFlow(...)
loadMoreJournalEntriesFlow(...)
createJournalEntryFlow(...)
refreshJournalFlow(...)
```

### Events

```text
src/features/journal/journal-events.js
```

Owns UI event handlers and does not register document listeners itself.

### Logging

```text
src/features/journal/journal-logging.js
```

Owns payload builders for meaningful app events:

```text
createClientSelectedJournalEvent(...)
createClientCreatedJournalEvent(...)
createClientUpdatedJournalEvent(...)
createOptimizationActionStatusJournalEvent(...)
createSyncStatusJournalEvent(...)
createIntegrationStatusJournalEvent(...)
```

### Page details renderers

```text
renderJournalEntryDetailsPanel(...)
renderJournalJsonBlock(...)
```

These renderers keep before / after / metadata display inside the page layer.

## Next useful iterations

```text
1. Add AI recommendation and business-context save journal entries.
2. Add backend journal-service once endpoints exist.
3. Add de-duplication rules for noisy repeated events.
4. Add richer styling for JSON details if the current native details UI feels too plain.
```

## Known risks

```text
Journal can become a dumping ground if event types are not constrained.
Too many low-level events will make the timeline useless.
Entries need stable clientId and entity references to stay explainable.
Before/after payloads may contain sensitive data and should be filtered before storing.
```

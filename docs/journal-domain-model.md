# Journal domain model

## Status

Journal MVP is now registered, wired in the app shell and enabled as a module route.

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
src/pages/journal.js: created and registered
app shell runtime wiring: done
client-scope reset: done
route mode switch: done
journal-service.js: pending backend endpoints
```

## Product definition

Journal is the client-scoped operational history of DirectPilot AI.

It should answer:

```text
what happened
who/what triggered it
which client it belongs to
which feature produced it
which entity was affected
what changed
what happened next
```

Journal is not a generic changelog and not a dumping ground for every console-like event.

## Current module contracts

### Store

```text
src/features/journal/journal-store.js
```

Owns normalization, filters, grouping and entry payload helpers. Store must not call API, read DOM, attach listeners, render UI or read localStorage directly.

### Local MVP source

```text
src/features/journal/journal-local-source.js
```

Owns scoped local storage source methods:

```text
createJournalLocalSource(options)
readAll()
writeAll(entries)
list(query)
get(entryId)
create(input)
replace(entries)
clear()
```

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

### Page renderers

```text
src/features/journal/journal-page.js
```

Owns reusable HTML render helpers.

### Events

```text
src/features/journal/journal-events.js
```

Owns event handlers and does not register document listeners itself.

### Page module

```text
src/pages/journal.js
```

Owns:

```text
JOURNAL_PAGE_ID
journalPage
journalPageContract()
renderJournalContent(context)
```

## Routing contract

Current route mode:

```text
journal: module
```

Migration condition status:

```text
1. Backend or local MVP journal source exists. Done.
2. journal-store.js owns normalization and filters. Done.
3. journal-controller.js is wired to source/service. Done.
4. journal-page.js renders from context. Done.
5. journal-events.js owns event handlers. Done.
6. PAGE_CONTENT_RENDERERS can render Journal from app context. Done.
7. App shell owns Journal runtime state/source/listeners. Done.
8. Client-scoped reset clears Journal state. Done.
9. Route mode changed from reserved to module. Done.
```

## Next useful iterations

```text
1. Add real auto-logging for client.created / client.updated / client.selected.
2. Add optimization action status journal entries.
3. Add integrations/sync journal entries.
4. Replace local source with backend service when endpoints exist.
```

## Known risks

```text
Journal can become a dumping ground if event types are not constrained.
Too many low-level events will make the timeline useless.
Entries need stable clientId and entity references to stay explainable.
Before/after payloads may contain sensitive data and should be filtered before storing.
```

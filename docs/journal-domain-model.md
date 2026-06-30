# Journal domain model

## Status

`journal` is still a reserved route, but the feature module and page module are now registered.

Current route metadata:

```text
Route id: journal
Route mode: reserved
Feature scaffold: src/features/journal/*
Page module: src/pages/journal.js
```

Current extraction status:

```text
journal-store.js: created
journal-local-source.js: created
journal-controller.js: created
journal-page.js: created
journal-events.js: created
src/pages/journal.js: created and registered
journal-service.js: pending backend endpoints
app shell runtime wiring: pending
client-scope reset: pending
route mode switch: pending
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

## Entity model

Target entity:

```ts
type JournalEntry = {
  id: string;
  scope: 'client' | 'account' | 'system';
  clientId: string | null;
  occurredAt: string;
  createdAt: string;
  source: 'ai' | 'optimization' | 'integration' | 'sync' | 'business_context' | 'client' | 'system';
  category: 'recommendation' | 'action' | 'status' | 'data_change' | 'error' | 'note';
  type: string;
  severity: 'info' | 'success' | 'warning' | 'error';
  title: string;
  summary: string;
  actor: JournalActor;
  entity: JournalEntity | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
};
```

## Current module contracts

### Store

```text
src/features/journal/journal-store.js
```

Owns:

```text
createInitialJournalState()
createDefaultJournalFilters(overrides)
normalizeJournalEntry(payload)
normalizeJournalEntries(payload)
normalizeJournalActor(actor)
normalizeJournalEntity(entity)
createJournalQueryParams(filters)
createJournalEntryPayload(input)
filterJournalEntries(entries, filters)
groupJournalEntriesByDate(entries)
formatJournalEntryDate(value)
compareJournalEntriesNewestFirst(a, b)
```

Store must not call API, read DOM, attach listeners, render UI or read localStorage directly.

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

Controller receives dependencies explicitly and must not own DOM selectors.

### Page renderers

```text
src/features/journal/journal-page.js
```

Owns reusable HTML render helpers:

```text
createJournalPageRenderers(context)
renderJournalPage(context)
renderJournalFilters(context)
renderJournalTimeline(context)
renderJournalEntry(entry)
renderJournalEmptyState()
renderJournalLoadMore(context)
```

Page functions receive context and return HTML strings. They must not call backend or attach listeners.

### Events

```text
src/features/journal/journal-events.js
```

Owns event handlers:

```text
createJournalEventHandlers(context)
handleJournalClickEvent(event)
handleJournalChangeEvent(event)
handleJournalSubmitEvent(event)
```

Events functions receive context and event objects. They must not register document listeners themselves.

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

`src/pages/index.js` registers Journal in:

```text
APP_PAGES
PAGE_CONTRACTS
PAGE_CONTENT_RENDERERS
```

## Routing contract

Current route mode:

```text
journal: reserved
```

Target route mode after runtime wiring and reset:

```text
journal: module
```

Migration condition before changing route mode:

```text
1. Backend or local MVP journal source exists. Done.
2. `src/features/journal/journal-store.js` owns normalization and filters. Done.
3. `src/features/journal/journal-controller.js` is wired to source/service. Done.
4. `src/features/journal/journal-page.js` renders from context. Done.
5. `src/features/journal/journal-events.js` owns event handlers. Done.
6. `PAGE_CONTENT_RENDERERS` can render Journal from app context. Done.
7. App shell owns Journal runtime state/source/listeners. Pending.
8. Client-scoped reset clears Journal state. Pending.
9. Route mode can change from reserved to module. Pending.
```

## Migration order

```text
1. Create backend/local MVP source contract. Done: journal-local-source.js.
2. Create `src/features/journal/journal-store.js` with normalization and filters. Done.
3. Create controller/page around local source. Done.
4. Create events. Done.
5. Wire into page renderer. Done.
6. Wire Journal runtime in app shell.
7. Add journal state to client-scope reset.
8. Change route mode from reserved to module.
9. Create `src/features/journal/journal-service.js` once endpoints are available.
```

## Known risks

```text
Journal can become a dumping ground if event types are not constrained.
Too many low-level events will make the timeline useless.
Entries need stable clientId and entity references to stay explainable.
Before/after payloads may contain sensitive data and should be filtered before storing.
```

## Do not do yet

```text
Do not change route mode from reserved yet.
Do not log every UI click.
Do not store raw tokens, OAuth payloads or full API responses in Journal metadata.
Do not mix Journal with system debug logs.
```

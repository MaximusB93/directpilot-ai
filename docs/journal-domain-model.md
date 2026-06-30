# Journal domain model

## Status

`journal` is currently a reserved route, but the MVP data source, store, controller, page renderers and event handlers now exist.

Current route metadata:

```text
Route id: journal
Route mode: reserved
Frontend route module: none yet
Feature scaffold: src/features/journal/*
```

Current extraction status:

```text
journal-store.js: created
journal-local-source.js: created
journal-controller.js: created
journal-page.js: created
journal-events.js: created
journal-service.js: pending backend endpoints
src/pages/journal.js: pending
```

Do not create `src/pages/journal.js` until app wiring and client-scope reset are implemented.

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

## Primary use cases

```text
1. See the history of AI recommendations and optimization decisions for a client.
2. Audit applied or rejected optimization actions.
3. Review integration/sync events for debugging client data freshness.
4. Track meaningful business-context changes.
5. Explain to a specialist or client why a recommendation/action exists.
```

## Scope

Journal is client-scoped by default.

Every journal entry should have:

```text
clientId
occurredAt
source
category
type
severity
title
summary
```

Entries without `clientId` are allowed only for account-level/system events and must be explicitly marked as `scope: account` or `scope: system`.

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

Nested models:

```ts
type JournalActor = {
  kind: 'user' | 'ai' | 'system' | 'backend';
  id: string | null;
  label: string;
};

type JournalEntity = {
  kind: 'client' | 'campaign' | 'optimization_action' | 'business_context' | 'integration' | 'sync_job' | 'ai_recommendation';
  id: string | null;
  label: string;
};
```

## Event type groups

### AI

```text
ai.recommendation_generated
ai.chat_message_sent
ai.memory_note_saved
ai.model_changed
ai.prompt_debug_loaded
```

### Optimization

```text
optimization.plan_generated
optimization.action_created
optimization.action_status_changed
optimization.execution_preview_loaded
optimization.drafts_created
```

### Integrations

```text
integration.yandex_oauth_started
integration.yandex_connected
integration.yandex_account_bound
integration.yandex_account_unbound
integration.yandex_connection_failed
```

### Sync / performance

```text
sync.started
sync.completed
sync.failed
performance.summary_loaded
```

### Business context

```text
business_context.loaded
business_context.saved
business_context.reset
business_context.changed
```

### Clients

```text
client.created
client.updated
client.deleted
client.selected
```

### System

```text
system.error
system.warning
system.info
```

## MVP local source contract

Current file:

```text
src/features/journal/journal-local-source.js
```

Responsibilities:

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

The local source uses scoped `localStorage` through `scopedStorageKey()` and delegates normalization/filtering to `journal-store.js`.

The local source is temporary. Backend endpoints can replace it later without changing store/page contracts.

## Store contract

Current file:

```text
src/features/journal/journal-store.js
```

Current responsibilities:

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

Store must not:

```text
call apiFetch
read DOM
write DOM
attach listeners
render UI
read localStorage directly
```

## Controller contract

Current file:

```text
src/features/journal/journal-controller.js
```

Current responsibilities:

```text
loadJournalEntriesFlow(...)
loadMoreJournalEntriesFlow(...)
createJournalEntryFlow(...)
refreshJournalFlow(...)
```

Controller receives dependencies explicitly:

```text
state
source/service
filters
input
onStart
onSuccess
onError
onFinally
render
```

Controller must not own DOM selectors.

## Page contract

Current file:

```text
src/features/journal/journal-page.js
```

Current responsibilities:

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

## Events contract

Current file:

```text
src/features/journal/journal-events.js
```

Current responsibilities:

```text
createJournalEventHandlers(context)
handleJournalClickEvent(event)
handleJournalChangeEvent(event)
handleJournalSubmitEvent(event)
```

Events functions receive context and event objects. They must not register document listeners themselves.

## Service contract

Target file:

```text
src/features/journal/journal-service.js
```

Responsibilities after backend is available:

```text
fetchJournalEntries(query)
fetchClientJournalEntries(clientId, query)
fetchJournalEntry(entryId)
createJournalEntry(payload)
```

Service must only call backend and throw useful errors.

## UI behavior

Default page behavior:

```text
show entries for selected client
newest first
group by date
filter by source/category/severity
load more with cursor
show empty state if there are no entries
```

Journal should never mutate source entities. It displays history and can create entries, but it should not apply optimization actions or change integrations directly.

## Routing contract

Current route mode:

```text
journal: reserved
```

Target route mode after migration:

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
6. `PAGE_CONTENT_RENDERERS` can render Journal from app context. Pending.
7. Route mode can change from reserved to module. Pending.
```

## Client-scoped reset integration

Journal state is client-scoped by default and should be reset when selected client changes.

After implementation, add journal state to:

```text
src/app/client-scope-reset.js
```

Do not add it now because there is still no app-level journal state.

## Migration order

```text
1. Create backend/local MVP source contract. Done: journal-local-source.js.
2. Create `src/features/journal/journal-store.js` with normalization and filters. Done.
3. Create controller/page around local source. Done.
4. Create events. Done.
5. Wire into page renderer.
6. Add journal state to client-scope reset.
7. Change route mode from reserved to module.
8. Create `src/features/journal/journal-service.js` once endpoints are available.
```

## Known risks

```text
Journal can become a dumping ground if event types are not constrained.
Too many low-level events will make the timeline useless.
Entries need stable clientId and entity references to stay explainable.
AI-generated summaries should be stored as generated text, not re-generated every render.
Before/after payloads may contain sensitive data and should be filtered before storing.
```

## Do not do yet

```text
Do not create `src/pages/journal.js` before app wiring and reset exist.
Do not change route mode from reserved yet.
Do not log every UI click.
Do not store raw tokens, OAuth payloads or full API responses in Journal metadata.
Do not mix Journal with system debug logs.
```

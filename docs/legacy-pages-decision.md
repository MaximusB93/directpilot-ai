# Legacy pages decision

## Wordstat

`wordstat` remains a legacy standalone frontend area for now.

Current decision:

```text
Route id: wordstat
Route mode: legacy
Frontend module: src/wordstat.js
Migration status: keep separate until data/service/page contracts are clear
```

Reasoning:

- `src/wordstat.js` already has its own refactor track in `docs/wordstat-refactor.md`.
- It imports shared core helpers, but it is not yet part of the main page composer registry.
- Moving it into `src/pages/index.js` before its data contract is stabilized would only create decorative architecture. Decorative architecture is how projects grow mold.

Next safe step:

```text
Define Wordstat page contract, service boundaries and state ownership before wiring it into PAGE_CONTENT_RENDERERS.
```

## Journal

`journal` remains a reserved route.

Current decision:

```text
Route id: journal
Route mode: reserved
Frontend module: none yet
Migration status: keep route metadata only until backend/domain contract exists
```

Reasoning:

- The route is useful as a reserved product direction.
- There is no stable data source, event model or page content contract yet.
- Creating a fake page now would add UI surface without product behavior. Humans love that, users do not.

Next safe step:

```text
Define journal entity model, backend endpoints and intended workflow before creating src/pages/journal.js.
```

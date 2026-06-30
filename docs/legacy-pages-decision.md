# Legacy pages decision

## Wordstat

`wordstat` is no longer a legacy route. It is registered as a module route and rendered through the app page registry.

Current decision:

```text
Route id: wordstat
Route mode: module
Frontend page module: src/pages/wordstat.js
Runtime bridge: src/main.js imports src/wordstat.js
Migration status: module route registered; remaining legacy runtime bridge can be absorbed later
```

Reasoning:

- `src/pages/wordstat.js` is registered in `src/pages/index.js`.
- `src/main.js` owns the Wordstat sidebar entry and render map entry.
- `app.html` no longer loads standalone Wordstat scripts directly.
- `src/wordstat.js` still contains the remaining runtime bridge and temporarily imports legacy Wordstat patch modules.

Next safe step:

```text
Absorb remaining Wordstat runtime bridge and legacy patch modules into feature modules only after the current module route is verified in production.
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

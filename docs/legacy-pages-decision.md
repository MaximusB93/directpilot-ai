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

## Journal

`journal` is no longer a reserved route. It is registered as a module route and rendered through the app page registry.

Current decision:

```text
Route id: journal
Route mode: module
Frontend page module: src/pages/journal.js
Runtime: src/main.js owns Journal state/source/event wiring
Source: local MVP source
Migration status: module route enabled
```

Next safe step:

```text
Add meaningful auto-logging from clients, optimization, integrations and sync flows.
```

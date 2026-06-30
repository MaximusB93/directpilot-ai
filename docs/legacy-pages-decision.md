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
Auto-logging: v1 wired
Migration status: module route enabled with meaningful app event logging
```

Next safe step:

```text
Add Journal details UI and extend logging to AI/business-context events.
```

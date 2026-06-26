# Wordstat frontend refactor plan

`src/wordstat.js` is still a large module and should not be rewritten through the GitHub contents API unless the full file is available for replacement and validation.

Current safe direction:

1. Keep `app.html` loading Wordstat scripts as ES modules.
2. Move shared helpers to `src/core/` first.
3. Replace local helpers in `src/wordstat.js` only with a local checkout and `npm run build`.
4. Target helpers for the first local pass:
   - API base resolution and authorized fetch;
   - HTML escaping;
   - number and percent formatting;
   - selected client lookup.

Do not edit the large region arrays by hand unless the change is isolated and validated.

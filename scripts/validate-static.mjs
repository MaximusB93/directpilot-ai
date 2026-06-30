import { access, readFile } from 'node:fs/promises';

const requiredFiles = [
  'index.html',
  'login.html',
  'app.html',
  'favicon.svg',
  'src/styles.css',
  'src/app/routes.js',
  'src/app/router.js',
  'src/app/page-router.js',
  'src/app/state.js',
  'src/app/hash-route-bridge.js',
  'src/app/client-scope-reset.js',
  'src/components/index.js',
  'src/components/empty-state.js',
  'src/components/panel.js',
  'src/components/status-badge.js',
  'src/controllers/ai-controller.js',
  'src/controllers/ai-event-bindings.js',
  'src/controllers/clients-controller.js',
  'src/controllers/integrations-controller.js',
  'src/controllers/optimization-controller.js',
  'src/pages/index.js',
  'src/pages/dashboard.js',
  'src/pages/clients.js',
  'src/pages/integrations.js',
  'src/pages/business-context.js',
  'src/pages/ai-assistant.js',
  'src/pages/optimization.js',
  'src/pages/wordstat.js',
  'src/features/wordstat/index.js',
  'src/features/wordstat/wordstat-store.js',
  'src/features/wordstat/wordstat-service.js',
  'src/features/wordstat/wordstat-legacy-adapter.js',
  'src/features/wordstat/wordstat-controller.js',
  'src/features/wordstat/wordstat-page.js',
  'src/features/wordstat/wordstat-events.js',
  'src/features/journal/index.js',
  'src/features/journal/journal-store.js',
  'src/features/journal/journal-local-source.js',
  'src/features/journal/journal-controller.js',
  'src/features/journal/journal-page.js',
  'src/features/journal/journal-events.js',
  'src/main.js',
  'src/login.js',
  'src/data.js',
  'src/wordstat.js',
  'src/wordstat_date_fix.js',
  'src/wordstat_regions_patch.js',
  'src/wordstat_ai_chat.js',
  'src/wordstat_chart_hover.js',
  'src/business_context_autofill.js',
  'src/core/api.js',
  'src/core/format.js',
  'src/core/html.js',
  'src/core/ids.js',
  'src/core/session-api.js',
  'src/core/storage.js',
  'docs/frontend-architecture.md',
  'docs/legacy-pages-decision.md',
  'docs/wordstat-refactor.md',
  'docs/wordstat-page-contract.md',
  'docs/journal-domain-model.md',
];

await Promise.all(requiredFiles.map((file) => access(file)));
const files = Object.fromEntries(await Promise.all(requiredFiles.map(async (file) => [file, await readFile(file, 'utf8')])));

function has(file, value) {
  return files[file].includes(value);
}

function lacks(file, values) {
  return values.every((value) => !files[file].includes(value));
}

const checks = [
  ['app shells', has('index.html', 'id="app"') && has('login.html', 'data-page="login"') && has('app.html', 'data-page="app"')],
  ['routes guarded', has('src/app/routes.js', "mode: 'module'") && has('src/app/routes.js', "mode: 'reserved'")],
  ['wordstat runtime via main', has('src/main.js', "import './wordstat.js';") && lacks('app.html', ['src/wordstat.js', 'src/wordstat_date_fix.js', 'src/wordstat_regions_patch.js', 'src/wordstat_ai_chat.js', 'src/wordstat_chart_hover.js'])],
  ['wordstat wiring guarded', has('src/pages/index.js', '[WORDSTAT_PAGE_ID]: renderWordstatContent') && has('src/wordstat.js', 'createWordstatEventHandlers({') && lacks('src/main.js', ['apiFetch('])],
  ['journal exports', ['journal-store.js', 'journal-local-source.js', 'journal-controller.js', 'journal-page.js', 'journal-events.js'].every((name) => has('src/features/journal/index.js', name))],
  ['journal store pure', has('src/features/journal/journal-store.js', 'normalizeJournalEntry') && has('src/features/journal/journal-store.js', 'groupJournalEntriesByDate') && lacks('src/features/journal/journal-store.js', ['apiFetch', 'document.', 'localStorage'])],
  ['journal local source', has('src/features/journal/journal-local-source.js', 'createJournalLocalSource') && has('src/features/journal/journal-local-source.js', 'scopedStorageKey') && has('src/features/journal/journal-local-source.js', 'filterJournalEntries')],
  ['journal controller pure', has('src/features/journal/journal-controller.js', 'loadJournalEntriesFlow') && has('src/features/journal/journal-controller.js', 'createJournalEntryFlow') && lacks('src/features/journal/journal-controller.js', ['document.', 'querySelector', 'localStorage', 'apiFetch'])],
  ['journal page pure', has('src/features/journal/journal-page.js', 'createJournalPageRenderers') && has('src/features/journal/journal-page.js', 'renderJournalTimeline') && lacks('src/features/journal/journal-page.js', ['apiFetch', 'document.', 'addEventListener'])],
  ['journal events pure', has('src/features/journal/journal-events.js', 'createJournalEventHandlers') && has('src/features/journal/journal-events.js', 'handleJournalClickEvent') && has('src/features/journal/journal-events.js', 'data-journal-load-more') && lacks('src/features/journal/journal-events.js', ['document.', 'addEventListener', 'querySelector', 'localStorage', 'apiFetch'])],
  ['journal still reserved', has('src/app/routes.js', "mode: 'reserved'") && lacks('src/pages/index.js', ['journalPage', 'renderJournalContent'])],
  ['docs updated', has('docs/journal-domain-model.md', 'journal-events.js: created') && has('docs/journal-domain-model.md', 'Create events. Done.') && has('docs/frontend-architecture.md', 'Journal event handler scaffold created')],
  ['no seeded account data', has('src/data.js', 'export const clients = []')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

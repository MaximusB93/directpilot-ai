import { access, readFile } from 'node:fs/promises';

const requiredFiles = [
  'index.html',
  'login.html',
  'app.html',
  'favicon.svg',
  'src/styles.css',
  'src/app-wide-ui.css',
  'src/app-product-polish.css',
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
  'src/services/ai-service.js',
  'src/stores/ai-store.js',
  'src/pages/index.js',
  'src/pages/dashboard.js',
  'src/pages/clients.js',
  'src/pages/integrations.js',
  'src/pages/business-context.js',
  'src/pages/ai-assistant.js',
  'src/pages/optimization.js',
  'src/pages/wordstat.js',
  'src/pages/journal.js',
  'src/pages/settings.js',
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
  'src/features/journal/journal-logging.js',
  'src/main.js',
  'src/login.js',
  'src/data.js',
  'src/wordstat.js',
  'src/wordstat_date_fix.js',
  'src/wordstat_regions_patch.js',
  'src/wordstat_ai_chat.js',
  'src/wordstat_chart_hover.js',
  'src/wordstat-nav-dedupe.js',
  'src/app-interaction-final.css',
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

function functionBody(file, functionName) {
  const source = files[file];
  const match = source.match(new RegExp(`function\\s+${functionName}\\s*\\(\\)\\s*\\{([\\s\\S]*?)\\n\\}`));
  return match ? match[1] : '';
}

const checks = [
  ['app shells', has('index.html', 'id="app"') && has('login.html', 'data-page="login"') && has('app.html', 'data-page="app"')],
  ['routes module modes', has('src/app/routes.js', 'wordstat') && has('src/app/routes.js', 'journal') && has('src/app/routes.js', "mode: 'module'") && !has('src/app/routes.js', "mode: 'reserved'")],
  ['wordstat runtime via main', has('src/main.js', "import './wordstat.js';") && lacks('app.html', ['src/wordstat.js', 'src/wordstat_date_fix.js', 'src/wordstat_regions_patch.js', 'src/wordstat_ai_chat.js', 'src/wordstat_chart_hover.js'])],
  ['cabinet UI safety guards', has('app.html', 'src/app-interaction-final.css') && has('app.html', 'src/wordstat-nav-dedupe.js') && !has('app.html', 'src/app-ui-compat.js') && has('src/wordstat-nav-dedupe.js', 'dedupeWordstatNav') && has('src/app-interaction-final.css', 'pointer-events')],
  ['journal exports', ['journal-store.js', 'journal-local-source.js', 'journal-controller.js', 'journal-page.js', 'journal-events.js', 'journal-logging.js'].every((name) => has('src/features/journal/index.js', name))],
  ['journal store pure', has('src/features/journal/journal-store.js', 'normalizeJournalEntry') && has('src/features/journal/journal-store.js', 'groupJournalEntriesByDate') && lacks('src/features/journal/journal-store.js', ['apiFetch', 'document.', 'localStorage'])],
  ['journal source/controller/page/events', has('src/features/journal/journal-local-source.js', 'createJournalLocalSource') && has('src/features/journal/journal-controller.js', 'loadJournalEntriesFlow') && has('src/features/journal/journal-page.js', 'createJournalPageRenderers') && has('src/features/journal/journal-events.js', 'createJournalEventHandlers')],
  ['journal logging helpers', has('src/features/journal/journal-logging.js', 'createClientSelectedJournalEvent') && has('src/features/journal/journal-logging.js', 'createOptimizationActionStatusJournalEvent') && has('src/features/journal/journal-logging.js', 'createSyncStatusJournalEvent') && lacks('src/features/journal/journal-logging.js', ['document.', 'localStorage', 'apiFetch'])],
  ['journal details UI', has('src/features/journal/journal-page.js', 'renderJournalEntryDetailsPanel') && has('src/features/journal/journal-page.js', 'renderJournalJsonBlock') && has('src/features/journal/journal-page.js', 'data-journal-entry-more') && has('src/features/journal/journal-page.js', 'before / after / metadata')],
  ['journal page registry', has('src/pages/journal.js', 'renderJournalContent') && has('src/pages/index.js', '[JOURNAL_PAGE_ID]: renderJournalContent')],
  ['settings page registry', has('src/app/routes.js', 'settings') && has('src/pages/settings.js', 'renderSettingsContent') && has('src/pages/index.js', '[SETTINGS_PAGE_ID]: renderSettingsContent') && has('src/main.js', "settings: renderSettings")],
  ['journal app shell runtime', has('src/main.js', 'const journalSource = createJournalLocalSource();') && has('src/main.js', 'function renderJournal()') && has('src/main.js', 'journal: renderJournal,') && has('src/main.js', "activeView === 'journal'") && has('src/main.js', 'journalEventHandlers.handleJournalClickEvent(event);')],
  ['journal auto logging wired', has('src/main.js', 'function logJournalEvent') && has('src/main.js', 'createClientSelectedJournalEvent') && has('src/main.js', 'createClientCreatedJournalEvent') && has('src/main.js', 'createClientUpdatedJournalEvent') && has('src/main.js', 'createOptimizationActionStatusJournalEvent') && has('src/main.js', 'createSyncStatusJournalEvent') && has('src/main.js', 'createIntegrationStatusJournalEvent')],
  ['journal client scoped reset', has('src/app/client-scope-reset.js', 'journalLoadedFor') && has('src/main.js', 'journalState = createInitialJournalState();') && has('src/main.js', 'journalState.filters = createDefaultJournalFilters')],
  ['main no direct api helper calls', lacks('src/main.js', ['apiFetch('])],
  ['ai model state is non-recursive', functionBody('src/main.js', 'currentAiModelState') && !functionBody('src/main.js', 'currentAiModelState').includes('activeAiBudget(')],
  ['ai settings moved to settings page', has('src/pages/settings.js', 'data-ai-model') && lacks('src/pages/ai-assistant.js', ['data-ai-model', 'data-ai-custom-model', 'openrouter/auto', 'Своя модель OpenRouter'])],
  ['ai chat has internal scroll guard', has('src/pages/ai-assistant.js', 'data-ai-chat-messages') && has('src/app-product-polish.css', 'scrollbar-gutter: stable') && has('src/app-product-polish.css', 'overscroll-behavior: contain')],
  ['api timeout tiers', has('src/core/api.js', 'DEFAULT_API_REQUEST_TIMEOUT_MS = 25 * 1000') && has('src/core/api.js', 'AI_API_REQUEST_TIMEOUT_MS = 70 * 1000') && has('src/core/api.js', '...fetchOptions')],
  ['ai endpoints use extended timeout', ['generateAiInsight', 'requestAiChat', 'fetchClientAiRecommendations'].every((name) => has('src/services/ai-service.js', name)) && has('src/services/ai-service.js', 'timeoutMs: AI_API_REQUEST_TIMEOUT_MS') && has('src/services/ai-service.js', "timeoutErrorCode: 'ai_request_timeout'")],
  ['frontend token budgets match backend', has('src/stores/ai-store.js', 'maxTokens: 1200') && has('src/stores/ai-store.js', 'maxTokens: 2500') && has('src/stores/ai-store.js', 'maxTokens: 5000') && has('src/stores/ai-store.js', 'status?.presets')],
  ['ai preset travels with requests', has('src/stores/ai-store.js', 'ai_preset: preset') && has('src/controllers/ai-controller.js', 'ai_preset: preset') && has('src/main.js', 'ai_preset: aiFeatureState.model.selectedPreset')],
  ['staged audit quick actions', has('src/pages/ai-assistant.js', 'data-ai-audit-start="full_account"') && has('src/pages/ai-assistant.js', 'data-ai-audit-start="critical_issues"') && lacks('src/pages/ai-assistant.js', ['data-ai-prompt="audit"', 'data-ai-prompt="critical"'])],
  ['heavy audit bypasses chat request', has('src/main.js', 'aiStore.requiresStagedAudit(text)') && has('src/main.js', "await startAiAudit('full_account', text)")],
  ['staged audit persistence and polling', has('src/main.js', 'directpilot_ai_audit_job_') && has('src/main.js', 'Math.max(1500') && has('src/main.js', 'isTerminalAiAuditStatus') && has('src/main.js', 'restoreAiAuditJob')],
  ['staged audit result UI', has('src/pages/ai-assistant.js', 'Результат аудита') && has('src/pages/ai-assistant.js', 'data-ai-audit-retry') && has('src/pages/ai-assistant.js', 'data-ai-audit-cancel')],
  ['no seeded account data', has('src/data.js', 'export const clients = []')],
  ['docs updated', has('docs/journal-domain-model.md', 'details UI: done') && has('docs/frontend-architecture.md', 'Journal details UI wired')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

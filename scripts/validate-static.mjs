import { access, readFile } from 'node:fs/promises';
import { renderSafeMarkdown } from '../src/core/markdown.js';
import { renderAiAuditResult } from '../src/pages/ai-assistant.js';
import { escapeHtml } from '../src/core/html.js';

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
  'src/core/markdown.js',
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

function appearsInOrder(file, values) {
  let previousIndex = -1;
  return values.every((value) => {
    const index = files[file].indexOf(value, previousIndex + 1);
    if (index < 0) return false;
    previousIndex = index;
    return true;
  });
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
  ['ai endpoints use extended timeout', ['generateAiInsight', 'requestAiChat', 'fetchClientAiRecommendations'].every((name) => has('src/services/ai-service.js', name)) && has('src/services/ai-service.js', 'AI_API_REQUEST_TIMEOUT_MS') && has('src/services/ai-service.js', "'ai_request_timeout'")],
  ['frontend token budgets match backend', has('src/stores/ai-store.js', 'maxTokens: 1200') && has('src/stores/ai-store.js', 'maxTokens: 2500') && has('src/stores/ai-store.js', 'maxTokens: 5000') && has('src/stores/ai-store.js', 'status?.presets')],
  ['ai preset travels with requests', has('src/stores/ai-store.js', 'ai_preset: preset') && has('src/controllers/ai-controller.js', 'ai_preset: preset') && has('src/main.js', 'ai_preset: aiFeatureState.model.selectedPreset')],
  ['staged audit quick actions', has('src/pages/ai-assistant.js', 'data-ai-audit-start="full_account"') && has('src/pages/ai-assistant.js', 'data-ai-audit-start="critical_issues"') && lacks('src/pages/ai-assistant.js', ['data-ai-prompt="audit"', 'data-ai-prompt="critical"'])],
  ['heavy audit bypasses chat request', has('src/main.js', 'aiStore.requiresStagedAudit(text)') && has('src/main.js', "await startAiAudit('full_account', text)")],
  ['staged audit persistence and polling', has('src/main.js', 'directpilot_ai_audit_job_') && has('src/main.js', 'Math.max(1500') && has('src/main.js', 'isTerminalAiAuditStatus') && has('src/main.js', 'restoreAiAuditJob')],
  ['staged audit result UI', has('src/pages/ai-assistant.js', 'Результат аудита') && has('src/pages/ai-assistant.js', 'data-ai-audit-retry') && has('src/pages/ai-assistant.js', 'data-ai-audit-cancel')],
  ['staged audit structured result', has('src/pages/ai-assistant.js', 'renderAiAuditResult') && has('src/pages/ai-assistant.js', 'Что проанализировано') && has('src/pages/ai-assistant.js', 'data-ai-audit-compact-retry')],
  ['adaptive audit progress', ['classify_campaigns', 'create_investigation_plan', 'collect_drilldowns', 'verify_hypotheses'].every((stage) => has('src/pages/ai-assistant.js', stage)) && has('src/pages/ai-assistant.js', 'AI запросил дополнительные данные:')],
  ['audit helper fallback UX', has('src/pages/ai-assistant.js', 'Аудит продолжен безопасно.') && has('src/pages/ai-assistant.js', 'helperProviderCallsCount') && lacks('src/pages/ai-assistant.js', ['helper_model || job.model'])],
  ['staged audit GET polling recovery', has('src/main.js', 'function refreshActiveAiAudit()') && has('src/main.js', 'aiAuditStatusCanAdvance') && has('src/main.js', 'void refreshActiveAiAudit()') && has('src/services/ai-service.js', '/reset')],
  ['staged audit timeout switches to polling', has('src/main.js', "error?.code === 'ai_audit_generation_timeout'") && has('src/main.js', 'scheduleAiAuditProgress(job.poll_after_ms, pollOnlyAfterRequest)')],
  ['staged audit assistant order', appearsInOrder('src/pages/ai-assistant.js', ['${renderAiAuditJob(context)}', '${renderAiQuickActions(context)}', '${renderAiChat(context)}'])],
  ['staged audit hidden debug panels', !has('src/pages/ai-assistant.js', '${renderAiChat(context)}\n    ${renderAiPromptDebugPanel(context)}') && !has('src/pages/ai-assistant.js', '${renderClientAiRecommendations(context)}\n  `;')],
  ['ai chat minimum height', has('src/app-product-polish.css', 'min-height: 520px') && has('src/app-product-polish.css', 'min-height: 360px')],
  ['audit source counters are explicit', has('src/pages/ai-assistant.js', 'выполнено по сохранённым данным') && has('src/pages/ai-assistant.js', 'live-попыток') && has('src/pages/ai-assistant.js', 'переходов к сохранённым данным') && has('src/pages/ai-assistant.js', 'unavailableDimensions')],
  ['audit findings grouped by verification', has('src/pages/ai-assistant.js', 'Подтверждённые проблемы') && has('src/pages/ai-assistant.js', 'Частично подтверждённые проблемы') && has('src/pages/ai-assistant.js', 'Опровергнутые гипотезы')],
  ['audit technical response is hidden', !has('src/pages/ai-assistant.js', 'class="aiAuditTechnicalDetails"') && !has('src/pages/ai-assistant.js', 'Технический ответ модели')],
  ['completed audit chat is compact', has('src/main.js', 'job.result?.structured') && has('src/main.js', 'auditJobId: job.job_id') && has('src/pages/ai-assistant.js', 'data-ai-audit-open')],
  ['assistant safe markdown', has('src/pages/ai-assistant.js', 'renderAiAssistantMarkdown(message.content)') && has('src/pages/ai-assistant.js', 'renderSafeMarkdown(value)') && has('src/pages/ai-assistant.js', '`<p>${escapeHtml(message.content)}</p>`') && has('src/core/markdown.js', 'export function renderSafeMarkdown') && has('src/core/markdown.js', 'noreferrer noopener')],
  ['staged audit timeout isolated', has('src/services/ai-service.js', 'AI_AUDIT_GENERATION_TIMEOUT_MS = 150 * 1000') && has('src/services/ai-service.js', 'options?.timeoutMs ?? AI_API_REQUEST_TIMEOUT_MS')],
  ['no seeded account data', has('src/data.js', 'export const clients = []')],
  ['docs updated', has('docs/journal-domain-model.md', 'details UI: done') && has('docs/frontend-architecture.md', 'Journal details UI wired')],
];

const failed = checks.filter(([, ok]) => !ok);
const markdownSmoke = renderSafeMarkdown('## Заголовок\n\n- пункт\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n<script>alert(1)</script> [bad](javascript:alert(1))');
if (!markdownSmoke.includes('<h2>Заголовок</h2>')
  || !markdownSmoke.includes('<ul><li>пункт</li></ul>')
  || !markdownSmoke.includes('<table>')
  || markdownSmoke.includes('<script>')
  || markdownSmoke.includes('href="javascript:')) {
  failed.push(['safe markdown runtime smoke', false]);
}
const auditSmoke = renderAiAuditResult({
  structured: {
    meta: { period: { date_from: '2026-06-10', date_to: '2026-07-09', days: 30 }, data_coverage: { campaigns: { available: true, analyzed: 1, total: 1 } }, model: 'test/model', output_budget_tokens: 10000 },
    executive_summary: 'Итог', data_quality: { status: 'sufficient' },
    critical_findings: [{ campaign_name: 'Кампания Бренд', problem: 'Проблема', fact: 'Факт', recommendation: 'Проверить', risk: 'high' }],
    opportunities: [],
    insufficient_data_campaigns: [{ campaign_name: 'Кампания РСЯ', reason: 'Мало кликов', recommendation: 'Собрать данные', next_data_needed: ['search_queries'] }],
    action_plan: [], prohibited_actions: [], limitations: [], conclusion: 'Вывод',
  },
  truncated: true,
  warnings: ['Ответ модели достиг лимита и мог быть обрезан.'],
}, '', escapeHtml, {
  timings: {},
  context_metadata: {
    investigation: {
      dataRequests: {
        planned: 3, allowed: 2, saved: 1, live: 0,
        statusCounts: { collected: 1, unavailable: 1, not_applicable: 1 },
        unavailableDimensions: ['placements'],
      },
    },
  },
});
if (!auditSmoke.includes('<p class="aiAuditPeriod">Период анализа: 10.06.2026–09.07.2026, 30 дней.')
  || auditSmoke.indexOf('Период анализа:') > auditSmoke.indexOf('Что проанализировано')
  || !auditSmoke.includes('Что проанализировано')
  || !auditSmoke.includes('Кампания Бренд')
  || !auditSmoke.includes('Выполнено по данным последней синхронизации DirectPilot: 1')
  || !auditSmoke.includes('площадки. Эти данные не учитывались в выводах')
  || !auditSmoke.includes('Неподтверждённые гипотезы')
  || !auditSmoke.includes('<strong>Кампания РСЯ</strong>: Мало кликов')
  || auditSmoke.includes('[object Object]')
  || !auditSmoke.includes('Ответ модели достиг лимита')
  || auditSmoke.includes('CampaignId')) {
  failed.push(['structured audit runtime smoke', false]);
}
const rawAuditFallbackSmoke = renderAiAuditResult({
  structured: null,
  fallbackMarkdown: '```json\n{"executive_summary":"must stay hidden"}\n```',
  warnings: [],
}, '', escapeHtml, {});
if (!rawAuditFallbackSmoke.includes('AI вернул результат в неподдерживаемом формате')
  || rawAuditFallbackSmoke.includes('must stay hidden')
  || rawAuditFallbackSmoke.includes('<pre>')) {
  failed.push(['raw audit JSON presentation guard', false]);
}
const technicalAuditSmoke = renderAiAuditResult({
  structured: null,
  fallbackMarkdown: 'AI вернул результат в неподдерживаемом формате.',
  technicalResponse: '<script>must-not-run</script>',
  structuredParsing: { errorCode: 'json_schema_validation_failed' },
  warnings: [],
}, '', escapeHtml, {});
if (technicalAuditSmoke.includes('must-not-run')
  || technicalAuditSmoke.includes('<pre>')
  || technicalAuditSmoke.includes('Технический ответ модели')) {
  failed.push(['audit technical response runtime smoke', false]);
}
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

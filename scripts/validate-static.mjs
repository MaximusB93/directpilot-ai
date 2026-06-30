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
  'src/services/clients-service.js',
  'src/services/integrations-service.js',
  'src/services/business-context-service.js',
  'src/services/sync-service.js',
  'src/services/performance-service.js',
  'src/services/optimization-service.js',
  'src/services/ai-service.js',
  'src/stores/client-store.js',
  'src/stores/ai-store.js',
  'src/stores/ai-feature-state.js',
  'src/stores/business-context-store.js',
  'src/stores/campaign-store.js',
  'src/stores/optimization-store.js',
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

const appHtml = files['app.html'];
const js = files['src/main.js'];
const routes = files['src/app/routes.js'];
const pagesIndex = files['src/pages/index.js'];
const wordstatPageModule = files['src/pages/wordstat.js'];
const wordstatLegacy = files['src/wordstat.js'];
const wordstatIndex = files['src/features/wordstat/index.js'];
const wordstatStore = files['src/features/wordstat/wordstat-store.js'];
const wordstatService = files['src/features/wordstat/wordstat-service.js'];
const wordstatAdapter = files['src/features/wordstat/wordstat-legacy-adapter.js'];
const wordstatController = files['src/features/wordstat/wordstat-controller.js'];
const wordstatPage = files['src/features/wordstat/wordstat-page.js'];
const wordstatEvents = files['src/features/wordstat/wordstat-events.js'];
const frontendArchitecture = files['docs/frontend-architecture.md'];
const wordstatContract = files['docs/wordstat-page-contract.md'];
const journalDomainModel = files['docs/journal-domain-model.md'];

const checks = [
  ['app shell files', files['index.html'].includes('id="app"') && files['login.html'].includes('data-page="login"') && appHtml.includes('data-page="app"')],
  ['app routing modules', routes.includes('APP_ROUTES') && routes.includes('LEGACY_ROUTE_REDIRECTS') && routes.includes('normalizeAppRouteId') && routes.includes('getRouteMode')],
  ['route mode metadata guarded', routes.includes("wordstat") && routes.includes("mode: 'legacy'") && routes.includes("journal") && routes.includes("mode: 'reserved'")],
  ['main imports wordstat runtime', js.includes("import './wordstat.js';")],
  ['main wordstat route wiring', js.includes("{ id: 'wordstat', label: 'Wordstat', icon: '📈' }") && js.includes('function wordstatPageContext()') && js.includes("resolvePageContentRenderer('wordstat')") && js.includes('function renderWordstat()') && js.includes('wordstat: renderWordstat,')],
  ['app html removed standalone wordstat scripts', !appHtml.includes('src/wordstat.js') && !appHtml.includes('src/wordstat_date_fix.js') && !appHtml.includes('src/wordstat_regions_patch.js') && !appHtml.includes('src/wordstat_ai_chat.js') && !appHtml.includes('src/wordstat_chart_hover.js')],
  ['app html keeps app shell scripts', appHtml.includes('src/app/hash-route-bridge.js') && appHtml.includes('src/main.js') && appHtml.includes('src/business_context_autofill.js') && appHtml.includes('src/performance_range_panel.js')],
  ['wordstat legacy imports patch modules', wordstatLegacy.includes("import './wordstat_date_fix.js';") && wordstatLegacy.includes("import './wordstat_regions_patch.js';") && wordstatLegacy.includes("import './wordstat_ai_chat.js';") && wordstatLegacy.includes("import './wordstat_chart_hover.js';")],
  ['wordstat feature exports', wordstatIndex.includes('wordstat-store.js') && wordstatIndex.includes('wordstat-service.js') && wordstatIndex.includes('wordstat-legacy-adapter.js') && wordstatIndex.includes('wordstat-controller.js') && wordstatIndex.includes('wordstat-page.js') && wordstatIndex.includes('wordstat-events.js')],
  ['wordstat page module registered', wordstatPageModule.includes('WORDSTAT_PAGE_ID') && wordstatPageModule.includes('wordstatPageContract') && wordstatPageModule.includes('renderWordstatContent') && wordstatPageModule.includes('data-wordstat-workspace') && pagesIndex.includes("from './wordstat.js'") && pagesIndex.includes('[WORDSTAT_PAGE_ID]: wordstatPage') && pagesIndex.includes('[WORDSTAT_PAGE_ID]: renderWordstatContent')],
  ['wordstat store pure', wordstatStore.includes('createWordstatRequestBody') && wordstatStore.includes('buildWordstatTotalSummary') && !wordstatStore.includes('apiFetch') && !wordstatStore.includes('document.') && !wordstatStore.includes('localStorage')],
  ['wordstat service owns backend calls', wordstatService.includes('fetchWordstatConnection') && wordstatService.includes('fetchWordstatDynamics') && wordstatService.includes('/wordstat/connection') && wordstatService.includes('/wordstat/dynamics/batch')],
  ['wordstat adapter wired', wordstatAdapter.includes('createWordstatLegacyApi') && wordstatLegacy.includes("from './features/wordstat/wordstat-legacy-adapter.js'") && wordstatLegacy.includes('createWordstatRequestBody(wordstatState.form') && !wordstatLegacy.includes('apiFetch(')],
  ['wordstat controller wired', wordstatController.includes('openWordstatFlow') && wordstatController.includes('submitWordstatDynamicsFlow') && wordstatController.includes('compareWordstatPeriodFlow') && wordstatController.includes('copyWordstatJsonFlow') && !wordstatController.includes('document.') && wordstatLegacy.includes('await openWordstatFlow({')],
  ['wordstat page renderers wired', wordstatPage.includes('createWordstatPageRenderers') && wordstatPage.includes('renderWordstatResult') && wordstatPage.includes('renderWordstatChart') && !wordstatPage.includes('apiFetch(') && !wordstatPage.includes('document.') && wordstatLegacy.includes('createWordstatPageRenderers({')],
  ['wordstat events wired', wordstatEvents.includes('createWordstatEventHandlers') && wordstatEvents.includes('handleClickEvent') && wordstatEvents.includes('handleSubmitEvent') && !wordstatEvents.includes('document.') && !wordstatEvents.includes('addEventListener') && wordstatLegacy.includes('createWordstatEventHandlers({')],
  ['wordstat auto open bridge', wordstatLegacy.includes('let wordstatAutoOpening = false') && wordstatLegacy.includes('function shouldAutoOpenWordstatView()') && wordstatLegacy.includes("document.body.dataset.view === WORDSTAT_VIEW_ID") && wordstatLegacy.includes('async function autoOpenWordstatView()') && wordstatLegacy.includes('void autoOpenWordstatView();')],
  ['main no direct api helper calls', !js.includes('apiFetch(')],
  ['no seeded account data', files['src/data.js'].includes('export const clients = []')],
  ['wordstat docs updated', wordstatContract.includes('app.html standalone Wordstat scripts: removed') && wordstatContract.includes('Remove standalone Wordstat scripts from app.html. Done.') && wordstatContract.includes('Change route mode from legacy to module')],
  ['frontend architecture docs updated', frontendArchitecture.includes('Wordstat standalone scripts removed from app.html') && frontendArchitecture.includes("src/main.js -> import './wordstat.js'") && frontendArchitecture.includes('Change Wordstat route mode from legacy to module')],
  ['journal domain model docs', journalDomainModel.includes('JournalEntry') && journalDomainModel.includes('src/features/journal/')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

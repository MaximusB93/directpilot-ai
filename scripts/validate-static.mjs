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
  'src/features/wordstat/index.js',
  'src/features/wordstat/wordstat-store.js',
  'src/features/wordstat/wordstat-service.js',
  'src/features/wordstat/wordstat-legacy-adapter.js',
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

const js = files['src/main.js'];
const styles = files['src/styles.css'];
const routes = files['src/app/routes.js'];
const clientScopeReset = files['src/app/client-scope-reset.js'];
const frontendArchitecture = files['docs/frontend-architecture.md'];
const legacyPagesDecision = files['docs/legacy-pages-decision.md'];
const wordstatContract = files['docs/wordstat-page-contract.md'];
const journalDomainModel = files['docs/journal-domain-model.md'];
const integrationsPage = files['src/pages/integrations.js'];
const businessContextPage = files['src/pages/business-context.js'];
const wordstatLegacy = files['src/wordstat.js'];
const wordstatIndex = files['src/features/wordstat/index.js'];
const wordstatStore = files['src/features/wordstat/wordstat-store.js'];
const wordstatService = files['src/features/wordstat/wordstat-service.js'];
const wordstatLegacyAdapter = files['src/features/wordstat/wordstat-legacy-adapter.js'];
const clientsController = files['src/controllers/clients-controller.js'];
const integrationsController = files['src/controllers/integrations-controller.js'];
const optimizationController = files['src/controllers/optimization-controller.js'];
const aiController = files['src/controllers/ai-controller.js'];
const aiEventBindings = files['src/controllers/ai-event-bindings.js'];

const checks = [
  ['app shell files', files['index.html'].includes('id="app"') && files['login.html'].includes('data-page="login"') && files['app.html'].includes('data-page="app"')],
  ['app routing modules', routes.includes('APP_ROUTES') && routes.includes('LEGACY_ROUTE_REDIRECTS') && routes.includes('normalizeAppRouteId') && routes.includes('getRouteMode')],
  ['client scoped reset helper', clientScopeReset.includes('createClientScopeResetPatch') && clientScopeReset.includes('applyClientScopeResetPatch') && clientScopeReset.includes('optimizationExecutionPreviews')],
  ['main client scoped reset wiring', js.includes("from './app/client-scope-reset.js'") && js.includes('applyClientScopeResetPatch((patch) => {') && js.includes('optimizationExecutionPreviews = patch.optimizationExecutionPreviews')],
  ['main old client reset block removed', !js.includes('businessContext = null;\n    businessContextDraft = null;\n    clientYandexIntegration = null;') && !js.includes("optimizationActionsLoadedFor = '';\n    resetAiClientScopedState")],
  ['route mode metadata', routes.includes("mode: 'legacy'") && routes.includes("mode: 'reserved'") && routes.includes('wordstat') && routes.includes('journal')],
  ['journal remains reserved', routes.includes("journal: {") && routes.includes("mode: 'reserved'") && !files['src/pages/index.js'].includes('journal')],
  ['main route normalization import', js.includes("import { normalizeAppRouteId } from './app/routes.js'")],
  ['main route normalization delegation', js.includes('return page === \'app\' ? normalizeAppRouteId(view) : view;')],
  ['main legacy route block removed', !js.includes('const primaryAppViews') && !js.includes('const legacyViewRedirects') && !js.includes('primaryAppViews.has(view)')],
  ['main auth session persistence', js.includes('const sessionToken = data.session_token || data.access_token') && js.includes('const sessionEmail = data.email || authEmail') && js.includes('saveSession(sessionToken, sessionEmail);')],
  ['main auth session mismatch removed', !js.includes('saveSession(authEmail, data.access_token)') && !js.includes('saveSession(authEmail, data.session_token)')],
  ['login canonical session persistence', files['src/login.js'].includes('saveSession(result.session_token, result.email)')],
  ['storage saveSession signature', files['src/core/storage.js'].includes('export function saveSession(sessionToken, email)')],
  ['page content composers', files['src/pages/dashboard.js'].includes('renderDashboardContent') && files['src/pages/clients.js'].includes('renderClientsContent') && files['src/pages/integrations.js'].includes('renderIntegrationsContent') && files['src/pages/business-context.js'].includes('renderBusinessContextContent') && files['src/pages/ai-assistant.js'].includes('renderAiAssistantContent') && files['src/pages/optimization.js'].includes('renderOptimizationContent')],
  ['component scaffold', files['src/components/index.js'].includes('status-badge') && files['src/components/status-badge.js'].includes('renderStatusBadge') && files['src/components/panel.js'].includes('renderPanel') && files['src/components/empty-state.js'].includes('renderEmptyState')],
  ['integrations UI primitive wiring', integrationsPage.includes("from '../components/index.js'") && integrationsPage.includes('renderPanel({') && integrationsPage.includes('renderStatusBadge({') && integrationsPage.includes('renderEmptyState({')],
  ['business context UI primitive wiring', businessContextPage.includes("from '../components/index.js'") && businessContextPage.includes('renderPanel({') && businessContextPage.includes('renderStatusBadge({') && businessContextPage.includes('renderEmptyState({')],
  ['shared UI primitive styles', styles.includes('.statusBadge') && styles.includes('.statusBadge--success') && styles.includes('.emptyState') && styles.includes('.panelActions') && styles.includes('.panelSubtitle')],
  ['wordstat feature exports', wordstatIndex.includes('wordstat-store.js') && wordstatIndex.includes('wordstat-service.js') && wordstatIndex.includes('wordstat-legacy-adapter.js')],
  ['wordstat store scaffold', wordstatStore.includes('createDefaultWordstatForm') && wordstatStore.includes('createInitialWordstatState') && wordstatStore.includes('parseWordstatPhrases') && wordstatStore.includes('parseWordstatCustomRegions') && wordstatStore.includes('createWordstatRequestBody') && wordstatStore.includes('buildWordstatTotalSummary') && !wordstatStore.includes('apiFetch') && !wordstatStore.includes('document.') && !wordstatStore.includes('localStorage')],
  ['wordstat service scaffold', wordstatService.includes('fetchWordstatConnection') && wordstatService.includes('fetchWordstatDynamics') && wordstatService.includes("/wordstat/connection") && wordstatService.includes("/wordstat/dynamics/batch") && wordstatService.includes("../../core/api.js")],
  ['wordstat legacy adapter scaffold', wordstatLegacyAdapter.includes('createWordstatLegacyApi') && wordstatLegacyAdapter.includes('createWordstatRequestBody') && wordstatLegacyAdapter.includes('fetchWordstatConnection') && wordstatLegacyAdapter.includes('fetchWordstatDynamics') && wordstatLegacyAdapter.includes('loadDynamics')],
  ['wordstat legacy adapter wiring', wordstatLegacy.includes("from './features/wordstat/wordstat-legacy-adapter.js'") && wordstatLegacy.includes('await fetchWordstatConnection()') && wordstatLegacy.includes('await fetchWordstatDynamics(collectRequestBody())') && wordstatLegacy.includes('createWordstatRequestBody(wordstatState.form') && !wordstatLegacy.includes('apiFetch(')],
  ['wordstat remains legacy route', files['app.html'].includes('src/wordstat.js') && routes.includes("mode: 'legacy'")],
  ['client store scaffold', files['src/stores/client-store.js'].includes('loadSelectedClientId') && files['src/stores/client-store.js'].includes('saveSelectedClientId') && files['src/stores/client-store.js'].includes('normalizeBackendClient')],
  ['feature stores', files['src/stores/ai-feature-state.js'].includes('createAiFeatureState') && files['src/stores/business-context-store.js'].includes('createBusinessContextPayload') && files['src/stores/campaign-store.js'].includes('createCampaignStore') && files['src/stores/optimization-store.js'].includes('normalizeOptimizationAction')],
  ['services present', files['src/services/clients-service.js'].includes('fetchClients') && files['src/services/integrations-service.js'].includes('fetchYandexStatus') && files['src/services/business-context-service.js'].includes('fetchBusinessContext') && files['src/services/sync-service.js'].includes('runClientSync') && files['src/services/performance-service.js'].includes('fetchPerformanceSummary') && files['src/services/optimization-service.js'].includes('fetchOptimizationPlan') && files['src/services/ai-service.js'].includes('requestAiChat')],
  ['ai controllers', aiController.includes('loadAiStatusFlow') && aiController.includes('sendAiChatMessageFlow') && aiEventBindings.includes('handleAiClickEvent')],
  ['clients controller wiring', clientsController.includes('loadClientsFromApiFlow') && clientsController.includes('createClientFlow') && clientsController.includes('saveClientSettingsFlow') && clientsController.includes('deleteClientFlow') && js.includes('await loadClientsFromApiFlow({') && js.includes('await createClientFlow({') && js.includes('await saveClientSettingsFlow({') && js.includes('await deleteClientFlow({')],
  ['integrations controller wiring', integrationsController.includes('startYandexOAuthFlow') && integrationsController.includes('bindClientYandexAccountFlow') && js.includes('await startYandexOAuthFlow({') && js.includes('await bindClientYandexAccountFlow({')],
  ['optimization controller wiring', optimizationController.includes('loadOptimizationPlanFlow') && optimizationController.includes('updateOptimizationActionStatusFlow') && js.includes('await loadOptimizationPlanFlow({') && js.includes('await updateOptimizationActionStatusFlow({')],
  ['main no direct api helper calls', !js.includes('apiFetch(')],
  ['main clients inline flow removed', !js.includes('const payload = await clientsService.fetchClients()') && !js.includes('await clientsService.deleteClient(clientId)') && !js.includes('const formData = new FormData(clientForm);')],
  ['legacy pages decision', legacyPagesDecision.includes('wordstat') && legacyPagesDecision.includes('legacy') && legacyPagesDecision.includes('journal') && legacyPagesDecision.includes('reserved')],
  ['wordstat contract docs', wordstatContract.includes('legacy src/wordstat.js wiring: done') && wordstatContract.includes('src/wordstat.js no longer calls `apiFetch` directly') && wordstatContract.includes('Move async open/submit/compare/copy flows into wordstat-controller.js')],
  ['journal domain model docs', journalDomainModel.includes('JournalEntry') && journalDomainModel.includes('src/features/journal/') && journalDomainModel.includes('journal-store.js') && journalDomainModel.includes('journal-service.js') && journalDomainModel.includes('journal-controller.js') && journalDomainModel.includes('journal-page.js')],
  ['journal api contract docs', journalDomainModel.includes('GET /journal') && journalDomainModel.includes('GET /clients/{clientId}/journal') && journalDomainModel.includes('POST /journal')],
  ['frontend architecture docs', frontendArchitecture.includes('Wordstat legacy adapter wired') && frontendArchitecture.includes('Move Wordstat async open/submit/compare/copy flows')],
  ['wordstat refactor guard', wordstatLegacy.includes("from './features/wordstat/wordstat-legacy-adapter.js'") && files['docs/wordstat-refactor.md'].includes('src/wordstat.js')],
  ['no seeded account data', files['src/data.js'].includes('export const clients = []')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

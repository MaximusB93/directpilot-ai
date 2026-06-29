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
  'docs/wordstat-refactor.md',
];

await Promise.all(requiredFiles.map((file) => access(file)));

const files = Object.fromEntries(await Promise.all(requiredFiles.map(async (file) => [file, await readFile(file, 'utf8')])));

const js = files['src/main.js'];
const clientsController = files['src/controllers/clients-controller.js'];
const integrationsController = files['src/controllers/integrations-controller.js'];
const optimizationController = files['src/controllers/optimization-controller.js'];
const aiController = files['src/controllers/ai-controller.js'];
const aiEventBindings = files['src/controllers/ai-event-bindings.js'];
const frontendArchitecture = files['docs/frontend-architecture.md'];

const checks = [
  ['app shell files', files['index.html'].includes('id="app"') && files['login.html'].includes('data-page="login"') && files['app.html'].includes('data-page="app"')],
  ['app routing modules', files['src/app/routes.js'].includes('APP_ROUTES') && files['src/app/router.js'].includes('navigateToRoute') && files['src/app/page-router.js'].includes('resolvePageContentRenderer') && files['src/app/hash-route-bridge.js'].includes('markRouteResolution')],
  ['page content composers', files['src/pages/dashboard.js'].includes('renderDashboardContent') && files['src/pages/clients.js'].includes('renderClientsContent') && files['src/pages/integrations.js'].includes('renderIntegrationsContent') && files['src/pages/business-context.js'].includes('renderBusinessContextContent') && files['src/pages/ai-assistant.js'].includes('renderAiAssistantContent') && files['src/pages/optimization.js'].includes('renderOptimizationContent')],
  ['clients service layer', files['src/services/clients-service.js'].includes('fetchClients') && files['src/services/clients-service.js'].includes('createClient') && files['src/services/clients-service.js'].includes('updateClient') && files['src/services/clients-service.js'].includes('deleteClient')],
  ['integrations service layer', files['src/services/integrations-service.js'].includes('fetchYandexStatus') && files['src/services/integrations-service.js'].includes('startYandexOAuth') && files['src/services/integrations-service.js'].includes('bindClientYandexIntegration')],
  ['business/sync/performance/optimization/ai services', files['src/services/business-context-service.js'].includes('fetchBusinessContext') && files['src/services/sync-service.js'].includes('runClientSync') && files['src/services/performance-service.js'].includes('fetchPerformanceSummary') && files['src/services/optimization-service.js'].includes('fetchOptimizationPlan') && files['src/services/ai-service.js'].includes('requestAiChat')],
  ['client store scaffold', files['src/stores/client-store.js'].includes('loadSelectedClientId') && files['src/stores/client-store.js'].includes('saveSelectedClientId') && files['src/stores/client-store.js'].includes('normalizeBackendClient')],
  ['ai state stores', files['src/stores/ai-store.js'].includes('activeAiModel') && files['src/stores/ai-feature-state.js'].includes('createAiFeatureState')],
  ['feature stores', files['src/stores/business-context-store.js'].includes('createBusinessContextPayload') && files['src/stores/campaign-store.js'].includes('createCampaignStore') && files['src/stores/optimization-store.js'].includes('normalizeOptimizationAction')],
  ['ai controllers', aiController.includes('loadAiStatusFlow') && aiController.includes('sendAiChatMessageFlow') && aiEventBindings.includes('handleAiClickEvent')],
  ['optimization controller flows', optimizationController.includes('loadOptimizationPlanFlow') && optimizationController.includes('loadOptimizationActionsFlow') && optimizationController.includes('updateOptimizationActionStatusFlow')],
  ['integrations controller flows', integrationsController.includes('loadIntegrationStatusFlow') && integrationsController.includes('startYandexOAuthFlow') && integrationsController.includes('bindClientYandexAccountFlow')],
  ['clients controller flows', clientsController.includes('loadClientsFromApiFlow') && clientsController.includes('createClientFlow') && clientsController.includes('saveClientSettingsFlow') && clientsController.includes('deleteClientFlow')],
  ['clients controller helpers', clientsController.includes('createClientSettingsDraftFromForm') && clientsController.includes('createLocalClientSettingsUpdate') && clientsController.includes('createClientSettingsPayload')],
  ['clients controller service calls', clientsController.includes('clientsService.fetchClients') && clientsController.includes('clientsService.createClient') && clientsController.includes('clientsService.updateClient') && clientsController.includes('clientsService.deleteClient')],
  ['main clients controller import', js.includes("from './controllers/clients-controller.js'") && js.includes('loadClientsFromApiFlow') && js.includes('createClientFlow') && js.includes('createClientSettingsDraftFromForm') && js.includes('saveClientSettingsFlow') && js.includes('deleteClientFlow')],
  ['main clients controller delegation', js.includes('await loadClientsFromApiFlow({') && js.includes('await createClientFlow({') && js.includes('clientSettingsDraft = createClientSettingsDraftFromForm(form)') && js.includes('await saveClientSettingsFlow({') && js.includes('await deleteClientFlow({')],
  ['main clients inline flow removed', !js.includes('const payload = await clientsService.fetchClients()') && !js.includes('await clientsService.deleteClient(clientId)') && !js.includes('const formData = new FormData(clientForm);')],
  ['main existing controller wiring', js.includes('await startYandexOAuthFlow({') && js.includes('await loadOptimizationPlanFlow({') && js.includes('await loadAiStatusFlow({') && js.includes('handleAiClickEvent(event')],
  ['main no direct api helper calls', !js.includes('apiFetch(')],
  ['frontend architecture docs', frontendArchitecture.includes('Clients controller wired') && frontendArchitecture.includes('Router cleanup')],
  ['wordstat refactor guard', files['src/wordstat.js'].includes("from './core/api.js'") && files['docs/wordstat-refactor.md'].includes('src/wordstat.js')],
  ['no seeded account data', files['src/data.js'].includes('export const clients = []')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

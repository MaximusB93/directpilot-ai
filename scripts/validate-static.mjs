import { access, readFile } from 'node:fs/promises';

const requiredFiles = [
  'index.html',
  'login.html',
  'app.html',
  'favicon.svg',
  'src/styles.css',
  'src/app-product-polish.css',
  'src/app-layout-hotfix.css',
  'src/app/routes.js',
  'src/app/router.js',
  'src/app/page-router.js',
  'src/app/state.js',
  'src/app/hash-route-bridge.js',
  'src/controllers/ai-controller.js',
  'src/controllers/ai-event-bindings.js',
  'src/controllers/optimization-controller.js',
  'src/pages/index.js',
  'src/pages/dashboard.js',
  'src/pages/clients.js',
  'src/pages/integrations.js',
  'src/pages/business-context.js',
  'src/pages/ai-assistant.js',
  'src/pages/optimization.js',
  'src/services/index.js',
  'src/services/clients-service.js',
  'src/services/integrations-service.js',
  'src/services/business-context-service.js',
  'src/services/sync-service.js',
  'src/services/performance-service.js',
  'src/services/optimization-service.js',
  'src/services/ai-service.js',
  'src/stores/index.js',
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

const html = await readFile('index.html', 'utf8');
const login = await readFile('login.html', 'utf8');
const cabinet = await readFile('app.html', 'utf8');
const favicon = await readFile('favicon.svg', 'utf8');
const css = await readFile('src/styles.css', 'utf8');
const productPolishCss = await readFile('src/app-product-polish.css', 'utf8');
const layoutHotfixCss = await readFile('src/app-layout-hotfix.css', 'utf8');
const appRoutes = await readFile('src/app/routes.js', 'utf8');
const appRouter = await readFile('src/app/router.js', 'utf8');
const appPageRouter = await readFile('src/app/page-router.js', 'utf8');
const appState = await readFile('src/app/state.js', 'utf8');
const hashRouteBridge = await readFile('src/app/hash-route-bridge.js', 'utf8');
const aiController = await readFile('src/controllers/ai-controller.js', 'utf8');
const aiEventBindings = await readFile('src/controllers/ai-event-bindings.js', 'utf8');
const optimizationController = await readFile('src/controllers/optimization-controller.js', 'utf8');
const pagesRegistry = await readFile('src/pages/index.js', 'utf8');
const dashboardPage = await readFile('src/pages/dashboard.js', 'utf8');
const clientsPage = await readFile('src/pages/clients.js', 'utf8');
const integrationsPage = await readFile('src/pages/integrations.js', 'utf8');
const businessContextPage = await readFile('src/pages/business-context.js', 'utf8');
const aiAssistantPage = await readFile('src/pages/ai-assistant.js', 'utf8');
const optimizationPage = await readFile('src/pages/optimization.js', 'utf8');
const servicesIndex = await readFile('src/services/index.js', 'utf8');
const clientsService = await readFile('src/services/clients-service.js', 'utf8');
const integrationsService = await readFile('src/services/integrations-service.js', 'utf8');
const businessContextService = await readFile('src/services/business-context-service.js', 'utf8');
const syncService = await readFile('src/services/sync-service.js', 'utf8');
const performanceService = await readFile('src/services/performance-service.js', 'utf8');
const optimizationService = await readFile('src/services/optimization-service.js', 'utf8');
const aiService = await readFile('src/services/ai-service.js', 'utf8');
const storesIndex = await readFile('src/stores/index.js', 'utf8');
const clientStore = await readFile('src/stores/client-store.js', 'utf8');
const aiStore = await readFile('src/stores/ai-store.js', 'utf8');
const aiFeatureState = await readFile('src/stores/ai-feature-state.js', 'utf8');
const businessContextStore = await readFile('src/stores/business-context-store.js', 'utf8');
const campaignStore = await readFile('src/stores/campaign-store.js', 'utf8');
const optimizationStore = await readFile('src/stores/optimization-store.js', 'utf8');
const js = await readFile('src/main.js', 'utf8');
const loginJs = await readFile('src/login.js', 'utf8');
const data = await readFile('src/data.js', 'utf8');
const businessAutofill = await readFile('src/business_context_autofill.js', 'utf8');
const wordstatJs = await readFile('src/wordstat.js', 'utf8');
const coreApi = await readFile('src/core/api.js', 'utf8');
const coreIds = await readFile('src/core/ids.js', 'utf8');
const coreSessionApi = await readFile('src/core/session-api.js', 'utf8');
const coreStorage = await readFile('src/core/storage.js', 'utf8');
const coreFormat = await readFile('src/core/format.js', 'utf8');
const frontendArchitecture = await readFile('docs/frontend-architecture.md', 'utf8');
const wordstatRefactor = await readFile('docs/wordstat-refactor.md', 'utf8');

const bridgeIndex = cabinet.indexOf('src/app/hash-route-bridge.js');
const mainIndex = cabinet.indexOf('src/main.js');

const checks = [
  ['root mount point', html.includes('id="app"')],
  ['login page', login.includes('data-page="login"')],
  ['cabinet page', cabinet.includes('data-page="app"')],
  ['favicon asset', favicon.includes('<svg') && favicon.includes('DirectPilot AI')],
  ['favicon links', html.includes('/favicon.svg') && login.includes('/favicon.svg') && cabinet.includes('/favicon.svg')],
  ['theme color meta', html.includes('theme-color') && login.includes('theme-color') && cabinet.includes('theme-color')],
  ['stylesheet link', html.includes('src/styles.css')],
  ['product polish stylesheet', cabinet.includes('src/app-product-polish.css') && productPolishCss.includes('Product polish layer')],
  ['layout hotfix stylesheet', cabinet.includes('src/app-layout-hotfix.css') && layoutHotfixCss.includes('Hotfix for cabinet layout')],
  ['app routes registry', appRoutes.includes('APP_ROUTES') && appRoutes.includes('business-context') && appRoutes.includes('DEFAULT_ROUTE_ID') && appRoutes.includes('normalizeRouteId')],
  ['app router foundation', appRouter.includes('currentHashRoute') && appRouter.includes('navigateToRoute') && appRouter.includes('onRouteChange')],
  ['app page router', appPageRouter.includes('resolveAppPage') && appPageRouter.includes('resolvePageContentRenderer')],
  ['app state foundation', appState.includes('getAppState') && appState.includes('setSelectedClientId') && appState.includes('directpilot:state-change')],
  ['hash route bridge', hashRouteBridge.includes('resolveAppPage') && hashRouteBridge.includes('markRouteResolution') && hashRouteBridge.includes('data-page-module')],
  ['hash route bridge before main', bridgeIndex !== -1 && mainIndex !== -1 && bridgeIndex < mainIndex],
  ['pages registry', pagesRegistry.includes('APP_PAGES') && pagesRegistry.includes('PAGE_CONTRACTS') && pagesRegistry.includes('PAGE_CONTENT_RENDERERS')],
  ['dashboard content composer', dashboardPage.includes('renderDashboardContent') && dashboardPage.includes('renderDashboardIntro')],
  ['clients content composer', clientsPage.includes('content-composer-ready') && clientsPage.includes('renderClientsContent')],
  ['business context content composer', businessContextPage.includes('content-composer-ready') && businessContextPage.includes('renderBusinessContextContent')],
  ['business context content registry', pagesRegistry.includes('renderBusinessContextContent') && pagesRegistry.includes('[BUSINESS_CONTEXT_PAGE_ID]: renderBusinessContextContent')],
  ['integrations content composer', integrationsPage.includes('content-composer-ready') && integrationsPage.includes('renderIntegrationsContent')],
  ['integrations content registry', pagesRegistry.includes('renderIntegrationsContent') && pagesRegistry.includes('[INTEGRATIONS_PAGE_ID]: renderIntegrationsContent')],
  ['ai assistant content composer', aiAssistantPage.includes('content-composer-ready') && aiAssistantPage.includes('renderAiAssistantContent')],
  ['ai assistant content registry', pagesRegistry.includes('renderAiAssistantContent') && pagesRegistry.includes('[AI_ASSISTANT_PAGE_ID]: renderAiAssistantContent')],
  ['optimization content composer', optimizationPage.includes('content-composer-ready') && optimizationPage.includes('renderOptimizationContent')],
  ['optimization content registry', pagesRegistry.includes('renderOptimizationContent') && pagesRegistry.includes('[OPTIMIZATION_PAGE_ID]: renderOptimizationContent')],
  ['services index exports', servicesIndex.includes('clients-service') && servicesIndex.includes('integrations-service') && servicesIndex.includes('ai-service')],
  ['clients service layer', clientsService.includes('fetchClients') && clientsService.includes('createClient') && clientsService.includes('updateClient') && clientsService.includes('deleteClient')],
  ['integrations service layer', integrationsService.includes('startYandexOAuth') && integrationsService.includes('fetchClientYandexIntegration') && integrationsService.includes('bindClientYandexIntegration')],
  ['business context service layer', businessContextService.includes('fetchBusinessContext') && businessContextService.includes('saveBusinessContext') && businessContextService.includes('saveBusinessContextMemoryNote')],
  ['sync service layer', syncService.includes('runClientSync') && syncService.includes('fetchSyncJobs')],
  ['performance service layer', performanceService.includes('fetchPerformanceSummary')],
  ['optimization service layer', optimizationService.includes('fetchOptimizationPlan') && optimizationService.includes('fetchOptimizationActions') && optimizationService.includes('fetchOptimizationExecutionPreview')],
  ['ai service layer', aiService.includes('fetchOpenRouterStatus') && aiService.includes('requestAiChat') && aiService.includes('fetchClientAiRecommendations') && aiService.includes('generateAiInsight')],
  ['stores exports', storesIndex.includes('client-store') && storesIndex.includes('ai-store') && storesIndex.includes('ai-feature-state') && storesIndex.includes('business-context-store') && storesIndex.includes('campaign-store') && storesIndex.includes('optimization-store')],
  ['client store scaffold', clientStore.includes('loadSelectedClientId') && clientStore.includes('saveSelectedClientId') && clientStore.includes('ensureSelectedClientId')],
  ['ai store scaffold', aiStore.includes('createInitialAiChatState') && aiStore.includes('createInitialAiModelState') && aiStore.includes('CUSTOM_MODEL_VALUE')],
  ['ai store helpers', aiStore.includes('normalizeAiStatus') && aiStore.includes('activeAiModel') && aiStore.includes('activeAiBudget') && aiStore.includes('addAiChatMessage')],
  ['ai feature state facade', aiFeatureState.includes('createAiFeatureState') && aiFeatureState.includes('model: {') && aiFeatureState.includes('generation: {') && aiFeatureState.includes('chat: {')],
  ['business context store helpers', businessContextStore.includes('normalizeBusinessContext') && businessContextStore.includes('createBusinessContextPayload') && businessContextStore.includes('createBusinessContextDraftFromForm') && businessContextStore.includes('createBusinessContextForAi') && businessContextStore.includes('calculateBusinessContextCompletenessScore')],
  ['business context store field mapping', businessContextStore.includes('company_name') && businessContextStore.includes('companyName') && businessContextStore.includes('memory_notes') && businessContextStore.includes('memoryNotes')],
  ['campaign store scaffold', campaignStore.includes('DEFAULT_CAMPAIGN_FILTER') && campaignStore.includes('createCampaignStore') && campaignStore.includes('getCampaignOptions')],
  ['campaign store performance helpers', campaignStore.includes('getCampaignsFromPerformanceSummary') && campaignStore.includes('filterCampaignsBySelectedName')],
  ['optimization store helpers', optimizationStore.includes('normalizeOptimizationPlan') && optimizationStore.includes('normalizeOptimizationAction') && optimizationStore.includes('normalizeOptimizationPreview') && optimizationStore.includes('normalizeOptimizationActions') && optimizationStore.includes('getFilteredOptimizationActions') && optimizationStore.includes('replaceOptimizationAction')],
  ['optimization store field mapping', optimizationStore.includes('daily_budget_recommendations') && optimizationStore.includes('dailyBudgetRecommendations') && optimizationStore.includes('direct_payload') && optimizationStore.includes('directPayload')],
  ['ai controller state helpers', aiController.includes('createAiModelStateSnapshot') && aiController.includes('createAiChatStateSnapshot') && aiController.includes('createAiAssistantPageContext')],
  ['ai controller flow helpers', aiController.includes('loadAiStatusFlow') && aiController.includes('loadAiPromptDebugFlow') && aiController.includes('generateAiInsightFlow')],
  ['ai controller remaining flow helpers', aiController.includes('requestAiRecommendationsFlow') && aiController.includes('sendAiChatMessageFlow') && aiController.includes('saveAiMemoryNoteFlow')],
  ['ai event bindings helpers', aiEventBindings.includes('handleAiSubmitEvent') && aiEventBindings.includes('handleAiInputEvent') && aiEventBindings.includes('handleAiChangeEvent') && aiEventBindings.includes('handleAiClickEvent')],
  ['optimization controller flows', optimizationController.includes('loadOptimizationPlanFlow') && optimizationController.includes('loadOptimizationActionsFlow') && optimizationController.includes('createOptimizationDraftsFromPlanFlow') && optimizationController.includes('updateOptimizationActionStatusFlow') && optimizationController.includes('loadOptimizationExecutionPreviewFlow')],
  ['optimization controller services', optimizationController.includes('optimizationService.fetchOptimizationPlan') && optimizationController.includes('optimizationService.fetchOptimizationActions') && optimizationController.includes('optimizationService.saveOptimizationPlanAsDrafts') && optimizationController.includes('optimizationService.updateOptimizationAction') && optimizationController.includes('optimizationService.fetchOptimizationExecutionPreview')],
  ['frontend architecture docs', frontendArchitecture.includes('Optimization controller/store wired') && frontendArchitecture.includes('Move Integrations controller helpers')],
  ['landing module script', html.includes('type="module"') && html.includes('src/main.js')],
  ['login module script', login.includes('type="module"') && login.includes('src/login.js')],
  ['cabinet module scripts', cabinet.includes('type="module"') && cabinet.includes('src/main.js') && cabinet.includes('src/business_context_autofill.js')],
  ['data module import', js.includes("from './data.js'")],
  ['shared api module', coreApi.includes('export async function apiFetch') && coreApi.includes('export async function postJson')],
  ['shared id module', coreIds.includes('export function createClientId') && coreIds.includes('export function normalizeId')],
  ['shared session api module', coreSessionApi.includes('requestEmailCode') && coreSessionApi.includes('verifyEmailCode')],
  ['shared storage module', coreStorage.includes('export function scopedStorageKey') && coreStorage.includes('export function saveSession')],
  ['shared format module', coreFormat.includes('export function formatNumber') && coreFormat.includes('export function formatMoney')],
  ['wordstat core api import', wordstatJs.includes("from './core/api.js'") && wordstatJs.includes('apiFetch')],
  ['wordstat html import', wordstatJs.includes("from './core/html.js'") && wordstatJs.includes('escapeHtml')],
  ['wordstat format import', wordstatJs.includes("from './core/format.js'") && wordstatJs.includes('formatNumber') && wordstatJs.includes('formatPercent')],
  ['wordstat storage import', wordstatJs.includes("from './core/storage.js'") && wordstatJs.includes('scopedStorageKey')],
  ['wordstat no local api helpers', !wordstatJs.includes('function resolveApiBase') && !wordstatJs.includes('function getSessionToken') && !wordstatJs.includes('async function apiFetch')],
  ['wordstat no local html/format helpers', !wordstatJs.includes('function escapeHtml') && !wordstatJs.includes('function formatNumber') && !wordstatJs.includes('function formatPercent')],
  ['main core api imports', js.includes("from './core/api.js'") && js.includes('API_BASE') && js.includes('escapeHtml') && js.includes('saveApiBase')],
  ['main service imports', js.includes("from './services/clients-service.js'") && js.includes("from './services/sync-service.js'") && js.includes("from './services/ai-service.js'")],
  ['main service layer usage', js.includes('clientsService.fetchClients') && js.includes('syncService.runClientSync') && js.includes('performanceService.fetchPerformanceSummary') && js.includes('businessContextService.fetchBusinessContext') && js.includes('integrationsService.fetchYandexStatus') && js.includes('optimizationService.fetchOptimizationPlan') && js.includes('aiService.requestAiChat')],
  ['main no inline apiFetch calls', !js.includes('apiFetch(')],
  ['main no duplicated async', !js.includes('async async function')],
  ['main ai store import', js.includes("import * as aiStore from './stores/ai-store.js'") && js.includes('const CUSTOM_MODEL_VALUE = aiStore.CUSTOM_MODEL_VALUE')],
  ['main ai feature state import', js.includes("from './stores/ai-feature-state.js'") && js.includes('createAiFeatureState') && js.includes('resetAiClientScopedState')],
  ['main ai feature state wiring', js.includes('const aiFeatureState = createAiFeatureState()') && js.includes('aiFeatureState.model.status') && js.includes('aiFeatureState.generation.loading') && js.includes('aiFeatureState.chat.messages')],
  ['main no legacy ai globals', !js.includes('let aiStatus =') && !js.includes('let selectedAiModel =') && !js.includes('let aiChatMessages =') && !js.includes('let aiLoading =')],
  ['main business context store import', js.includes("import * as businessContextStore from './stores/business-context-store.js'")],
  ['main business context store delegation', js.includes('businessContextStore.normalizeBusinessContext(payload)') && js.includes('businessContextStore.createBusinessContextPayload(context)') && js.includes('businessContextStore.createBusinessContextDraftFromForm(form)') && js.includes('businessContextStore.createBusinessContextForAi(businessContext, businessContextDraft)')],
  ['main optimization store import', js.includes("import * as optimizationStore from './stores/optimization-store.js'")],
  ['main optimization store delegation', js.includes('optimizationStore.normalizeOptimizationPlan(payload)') && js.includes('optimizationStore.normalizeOptimizationAction(action)') && js.includes('optimizationStore.normalizeOptimizationPreview(payload)') && js.includes('optimizationStore.getFilteredOptimizationActions(optimizationActions, optimizationActionFilter)')],
  ['main optimization controller import', js.includes("from './controllers/optimization-controller.js'") && js.includes('loadOptimizationPlanFlow') && js.includes('loadOptimizationActionsFlow') && js.includes('loadOptimizationExecutionPreviewFlow')],
  ['main optimization controller delegation', js.includes('await loadOptimizationPlanFlow({') && js.includes('await loadOptimizationActionsFlow({') && js.includes('await createOptimizationDraftsFromPlanFlow({') && js.includes('await updateOptimizationActionStatusFlow({') && js.includes('await loadOptimizationExecutionPreviewFlow({')],
  ['main ai controller import', js.includes("from './controllers/ai-controller.js'") && js.includes('createAiModelStateSnapshot') && js.includes('createAiChatStateSnapshot') && js.includes('createAiAssistantPageContext')],
  ['main ai controller flow delegation', js.includes('await loadAiStatusFlow({') && js.includes('await loadAiPromptDebugFlow({') && js.includes('await generateAiInsightFlow({')],
  ['main ai remaining flow delegation', js.includes('await requestAiRecommendationsFlow({') && js.includes('await sendAiChatMessageFlow({') && js.includes('await saveAiMemoryNoteFlow({')],
  ['main ai event bindings import', js.includes("from './controllers/ai-event-bindings.js'") && js.includes('handleAiChangeEvent') && js.includes('handleAiClickEvent') && js.includes('handleAiInputEvent') && js.includes('handleAiSubmitEvent')],
  ['main ai event bindings delegation', js.includes('handleAiInputEvent(event') && js.includes('handleAiChangeEvent(event') && js.includes('handleAiSubmitEvent(event') && js.includes('handleAiClickEvent(event')],
  ['main clients content wiring', js.includes("const contentRenderer = resolvePageContentRenderer('clients')") && js.includes('return renderShell(contentRenderer({') && js.includes('selectedClient: currentClient()')],
  ['main campaign store wiring', js.includes("import * as campaignStore from './stores/campaign-store.js'") && js.includes('const campaignsStore = campaignStore.createCampaignStore()') && js.includes('return campaignsStore.getCampaignOptions(perfSummary)')],
  ['main business context content wiring', js.includes("import { renderBusinessContextPanel as renderBusinessContextPanelContent } from './pages/business-context.js'") && js.includes('function businessContextPageContext(compact = false)') && js.includes('return renderShell(contentRenderer(businessContextPageContext(false)))')],
  ['main integrations content wiring', js.includes('function integrationsPageContext()') && js.includes("const contentRenderer = resolvePageContentRenderer('integrations')") && js.includes('return renderShell(contentRenderer(integrationsPageContext()))')],
  ['main ai assistant content wiring', js.includes('function aiAssistantPageContext()') && js.includes("const contentRenderer = resolvePageContentRenderer('ai')") && js.includes('return renderShell(contentRenderer(aiAssistantPageContext()))')],
  ['main optimization content wiring', js.includes('function optimizationPageContext()') && js.includes("const contentRenderer = resolvePageContentRenderer('optimization')") && js.includes('return renderShell(contentRenderer(optimizationPageContext()))')],
  ['main shared storage imports', js.includes("from './core/storage.js'") && js.includes('getSessionToken')],
  ['main shared session api imports', js.includes("from './core/session-api.js'") && js.includes('requestEmailCode') && js.includes('verifyEmailCode')],
  ['business autofill core import', businessAutofill.includes("from './core/api.js'") && businessAutofill.includes('apiFetch')],
  ['wordstat refactor plan', wordstatRefactor.includes('src/wordstat.js') && wordstatRefactor.includes('npm run build')],
  ['standalone login auth', loginJs.includes("from './core/api.js'") && loginJs.includes("from './core/storage.js'")],
  ['email auth view', js.includes('renderLogin') && js.includes('requestEmailCode')],
  ['cabinet view', js.includes('renderDashboard')],
  ['audit view', js.includes('renderAudit')],
  ['recommendations view', js.includes('renderRecommendations')],
  ['responsive styles', css.includes('@media') && productPolishCss.includes('@media') && layoutHotfixCss.includes('@media')],
  ['no seeded account data', data.includes('export const clients = []') && !data.includes('fgrf.ru') && !data.includes('Интернет-магазин мебели')],
  ['client add form', js.includes('data-client-form') && js.includes('directpilot_clients')],
  ['autopilot rules', data.includes('autopilotRules')],
  ['integrations view', js.includes('renderIntegrations') && integrationsPage.includes('data-integration="yandex-direct"')],
  ['openrouter ai view', js.includes('renderAiAssistant') && aiService.includes('/ai/openrouter/generate') && css.includes('.aiGrid')],
  ['custom openrouter model input', js.includes('CUSTOM_MODEL_VALUE') && aiAssistantPage.includes('data-ai-custom-model') && js.includes('activeAiModel()')],
  ['client ai recommendations', aiService.includes('/clients/${clientId}/ai/recommendations') && css.includes('.aiDraftGrid')],
  ['mcp ai chat', aiService.includes('/ai/chat') && aiAssistantPage.includes('renderAiChat') && css.includes('.aiChatPanel')],
  ['no frontend auth bypass', !js.includes('demo-session') && !js.includes('data-demo-login')],
  ['no hardcoded OpenRouter secret', !js.includes('sk-or-') && !data.includes('sk-or-')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

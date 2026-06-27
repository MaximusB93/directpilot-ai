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
  'src/stores/campaign-store.js',
  'src/main.js',
  'src/login.js',
  'src/data.js',
  'src/wordstat.js',
  'src/business_context_autofill.js',
  'src/core/api.js',
  'src/core/date.js',
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
const campaignStore = await readFile('src/stores/campaign-store.js', 'utf8');
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
  ['app page router', appPageRouter.includes('resolveAppPage') && appPageRouter.includes('getPageRenderer') && appPageRouter.includes('resolvePageRenderer') && appPageRouter.includes('resolvePageContentRenderer')],
  ['app state foundation', appState.includes('getAppState') && appState.includes('setSelectedClientId') && appState.includes('directpilot:state-change')],
  ['hash route bridge', hashRouteBridge.includes('resolveAppPage') && hashRouteBridge.includes('markRouteResolution') && hashRouteBridge.includes('data-page-module')],
  ['hash route bridge before main', bridgeIndex !== -1 && mainIndex !== -1 && bridgeIndex < mainIndex],
  ['pages registry', pagesRegistry.includes('APP_PAGES') && pagesRegistry.includes('PAGE_CONTRACTS') && pagesRegistry.includes('PAGE_RENDERERS') && pagesRegistry.includes('PAGE_CONTENT_RENDERERS') && pagesRegistry.includes('clientsPageContract') && pagesRegistry.includes('integrationsPageContract')],
  ['clients page contract', clientsPage.includes('CLIENTS_PAGE_ID') && clientsPage.includes('legacyRenderer') && clientsPage.includes('renderClients')],
  ['integrations page contract', integrationsPage.includes('INTEGRATIONS_PAGE_ID') && integrationsPage.includes('legacyRenderer') && integrationsPage.includes('renderIntegrations')],
  ['business context page contract', businessContextPage.includes('BUSINESS_CONTEXT_PAGE_ID') && businessContextPage.includes('legacyRenderer') && businessContextPage.includes('renderBusinessContext')],
  ['ai assistant page contract', aiAssistantPage.includes('AI_ASSISTANT_PAGE_ID') && aiAssistantPage.includes('legacyRenderer') && aiAssistantPage.includes('renderAiAssistant')],
  ['optimization page contract', optimizationPage.includes('OPTIMIZATION_PAGE_ID') && optimizationPage.includes('legacyRenderer') && optimizationPage.includes('renderOptimization')],
  ['dashboard renderer adapter', dashboardPage.includes('renderDashboardPage') && dashboardPage.includes('legacyRenderDashboard') && dashboardPage.includes('content-composer-ready')],
  ['dashboard extracted builders', dashboardPage.includes('renderDashboardIntro') && dashboardPage.includes('renderDashboardNextStepPanel') && dashboardPage.includes('renderDashboardEmptyClientPanel') && dashboardPage.includes('renderDashboardConnectedPanels') && dashboardPage.includes('extractedBuilders')],
  ['dashboard content composer', dashboardPage.includes('renderDashboardContent') && dashboardPage.includes('renderReadinessPanel') && dashboardPage.includes('renderDashboardConnectedPanels')],
  ['clients content composer', clientsPage.includes('content-composer-ready') && clientsPage.includes('renderClientsContent') && clientsPage.includes('renderClientCreatePanel') && clientsPage.includes('renderClientSettingsPanel') && clientsPage.includes('renderClientGrid')],
  ['business context content composer', businessContextPage.includes('content-composer-ready') && businessContextPage.includes('renderBusinessContextIntro') && businessContextPage.includes('renderBusinessContextPanel') && businessContextPage.includes('renderBusinessContextContent')],
  ['business context content registry', pagesRegistry.includes('renderBusinessContextContent') && pagesRegistry.includes('[BUSINESS_CONTEXT_PAGE_ID]: renderBusinessContextContent')],
  ['services index exports', servicesIndex.includes('clients-service') && servicesIndex.includes('integrations-service') && servicesIndex.includes('ai-service')],
  ['clients service layer', clientsService.includes('fetchClients') && clientsService.includes('createClient') && clientsService.includes('updateClient') && clientsService.includes('deleteClient')],
  ['integrations service layer', integrationsService.includes('startYandexOAuth') && integrationsService.includes('fetchClientYandexIntegration') && integrationsService.includes('bindClientYandexIntegration')],
  ['business context service layer', businessContextService.includes('fetchBusinessContext') && businessContextService.includes('saveBusinessContext') && businessContextService.includes('saveBusinessContextMemoryNote')],
  ['sync service layer', syncService.includes('runClientSync') && syncService.includes('fetchSyncJobs')],
  ['performance service layer', performanceService.includes('fetchPerformanceSummary')],
  ['optimization service layer', optimizationService.includes('fetchOptimizationPlan') && optimizationService.includes('fetchOptimizationActions') && optimizationService.includes('fetchOptimizationExecutionPreview')],
  ['ai service layer', aiService.includes('fetchOpenRouterStatus') && aiService.includes('requestAiChat') && aiService.includes('fetchClientAiRecommendations')],
  ['stores exports', storesIndex.includes('client-store') && storesIndex.includes('ai-store') && storesIndex.includes('campaign-store')],
  ['client store scaffold', clientStore.includes('loadSelectedClientId') && clientStore.includes('saveSelectedClientId') && clientStore.includes('ensureSelectedClientId')],
  ['ai store scaffold', aiStore.includes('createInitialAiChatState') && aiStore.includes('createInitialAiModelState') && aiStore.includes('CUSTOM_MODEL_VALUE')],
  ['ai store expanded state', aiStore.includes('createInitialAiGenerationState') && aiStore.includes('DEFAULT_AI_STATUS') && aiStore.includes('AI_PRESETS')],
  ['ai store helpers', aiStore.includes('normalizeAiStatus') && aiStore.includes('activeAiModel') && aiStore.includes('activeAiBudget') && aiStore.includes('aiConversationForRequest') && aiStore.includes('addAiChatMessage')],
  ['ai store request builders', aiStore.includes('createAiChatRequestPayload') && aiStore.includes('createAiPromptDebugParams') && aiStore.includes('business_context') && aiStore.includes('conversation')],
  ['campaign store scaffold', campaignStore.includes('DEFAULT_CAMPAIGN_FILTER') && campaignStore.includes('createCampaignStore') && campaignStore.includes('getCampaignName') && campaignStore.includes('getCampaignOptions') && campaignStore.includes('normalizeCampaignFilter')],
  ['campaign store performance helpers', campaignStore.includes('getCampaignsFromPerformanceSummary') && campaignStore.includes('filterCampaignsBySelectedName') && campaignStore.includes('isCampaignSelected')],
  ['dashboard page contract', dashboardPage.includes('DASHBOARD_PAGE_ID') && dashboardPage.includes('dashboardPageContract') && dashboardPage.includes('renderDashboard')],
  ['frontend architecture docs', frontendArchitecture.includes('service layer') && frontendArchitecture.includes('renderDashboardContent') && frontendArchitecture.includes('campaign-store.js') && frontendArchitecture.includes('renderClients()')],
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
  ['main ai store initial state wiring', js.includes('aiStore.createInitialAiModelState()') && js.includes('aiStore.createInitialAiChatState()') && js.includes('aiStore.createInitialAiGenerationState()')],
  ['main ai current state adapters', js.includes('function currentAiModelState()') && js.includes('function currentAiChatState()') && js.includes('selectedCampaignName: aiChatSelectedCampaignName')],
  ['main ai store helper delegation', js.includes('return aiStore.activeAiModel(currentAiModelState())') && js.includes('return aiStore.activeAiBudget(currentAiModelState())') && js.includes('return aiStore.createAiChatRequestPayload({') && js.includes('return aiStore.createAiPromptDebugParams(currentAiModelState(), aiChatSelectedCampaignName)')],
  ['main ai chat store delegation', js.includes('aiStore.addAiChatMessage(currentAiChatState()') && js.includes('aiChatRequestPayload(text)') && js.includes('aiStore.normalizeAiStatus(await aiService.fetchOpenRouterStatus())')],
  ['main clients content wiring', js.includes("const contentRenderer = resolvePageContentRenderer('clients')") && js.includes('return renderShell(contentRenderer({') && js.includes('selectedClient: currentClient()') && js.includes('clientSettingsDraft') && js.includes('clientSettingsSaving') && js.includes('clientSettingsStatus')],
  ['main campaign store wiring', js.includes("import * as campaignStore from './stores/campaign-store.js'") && js.includes('const campaignsStore = campaignStore.createCampaignStore()') && js.includes('return campaignsStore.getCampaignOptions(perfSummary)')],
  ['main business context content wiring', js.includes("import { renderBusinessContextPanel as renderBusinessContextPanelContent } from './pages/business-context.js'") && js.includes('function businessContextPageContext(compact = false)') && js.includes('return renderBusinessContextPanelContent(businessContextPageContext(compact))') && js.includes("const contentRenderer = resolvePageContentRenderer('business-context')") && js.includes('return renderShell(contentRenderer(businessContextPageContext(false)))')],
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
  ['integrations view', js.includes('renderIntegrations') && js.includes('data-integration="yandex-direct"')],
  ['openrouter ai view', js.includes('renderAiAssistant') && aiService.includes('/ai/openrouter/generate') && css.includes('.aiGrid')],
  ['custom openrouter model input', js.includes('CUSTOM_MODEL_VALUE') && js.includes('data-ai-custom-model') && js.includes('activeAiModel()')],
  ['client ai recommendations', aiService.includes('/clients/${clientId}/ai/recommendations') && css.includes('.aiDraftGrid')],
  ['mcp ai chat', aiService.includes('/ai/chat') && js.includes('renderAiChat') && css.includes('.aiChatPanel')],
  ['no frontend auth bypass', !js.includes('demo-session') && !js.includes('data-demo-login')],
  ['no hardcoded OpenRouter secret', !js.includes('sk-or-') && !data.includes('sk-or-')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

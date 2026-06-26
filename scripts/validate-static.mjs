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
  'src/app/state.js',
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
const appState = await readFile('src/app/state.js', 'utf8');
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
  ['app routes registry', appRoutes.includes('APP_ROUTES') && appRoutes.includes('DEFAULT_ROUTE_ID') && appRoutes.includes('normalizeRouteId')],
  ['app router foundation', appRouter.includes('currentHashRoute') && appRouter.includes('navigateToRoute') && appRouter.includes('onRouteChange')],
  ['app state foundation', appState.includes('getAppState') && appState.includes('setSelectedClientId') && appState.includes('directpilot:state-change')],
  ['frontend architecture docs', frontendArchitecture.includes('page-module architecture') && frontendArchitecture.includes('Do not rewrite `src/main.js` in one large commit')],
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
  ['main shared api imports', js.includes("from './core/api.js'") && js.includes('apiFetch')],
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
  ['openrouter ai view', js.includes('renderAiAssistant') && js.includes('/ai/openrouter/generate') && css.includes('.aiGrid')],
  ['custom openrouter model input', js.includes('CUSTOM_MODEL_VALUE') && js.includes('data-ai-custom-model') && js.includes('activeAiModel()')],
  ['client ai recommendations', js.includes('/clients/${selectedClientId}/ai/recommendations') && css.includes('.aiDraftGrid')],
  ['mcp ai chat', js.includes('/ai/chat') && js.includes('renderAiChat') && css.includes('.aiChatPanel')],
  ['no frontend auth bypass', !js.includes('demo-session') && !js.includes('data-demo-login')],
  ['no hardcoded OpenRouter secret', !js.includes('sk-or-') && !data.includes('sk-or-')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

import { access, readFile } from 'node:fs/promises';

const requiredFiles = [
  'index.html',
  'login.html',
  'app.html',
  'src/styles.css',
  'src/main.js',
  'src/login.js',
  'src/data.js',
  'src/business_context_autofill.js',
  'src/core/api.js',
  'src/core/date.js',
  'src/core/format.js',
  'src/core/html.js',
  'src/core/ids.js',
  'src/core/session-api.js',
  'src/core/storage.js',
];

await Promise.all(requiredFiles.map((file) => access(file)));

const html = await readFile('index.html', 'utf8');
const login = await readFile('login.html', 'utf8');
const cabinet = await readFile('app.html', 'utf8');
const css = await readFile('src/styles.css', 'utf8');
const js = await readFile('src/main.js', 'utf8');
const loginJs = await readFile('src/login.js', 'utf8');
const data = await readFile('src/data.js', 'utf8');
const businessAutofill = await readFile('src/business_context_autofill.js', 'utf8');
const coreApi = await readFile('src/core/api.js', 'utf8');
const coreIds = await readFile('src/core/ids.js', 'utf8');
const coreSessionApi = await readFile('src/core/session-api.js', 'utf8');
const coreStorage = await readFile('src/core/storage.js', 'utf8');
const coreFormat = await readFile('src/core/format.js', 'utf8');

const checks = [
  ['root mount point', html.includes('id="app"')],
  ['login page', login.includes('data-page="login"')],
  ['cabinet page', cabinet.includes('data-page="app"')],
  ['stylesheet link', html.includes('src/styles.css')],
  ['landing module script', html.includes('type="module"') && html.includes('src/main.js')],
  ['login module script', login.includes('type="module"') && login.includes('src/login.js')],
  ['cabinet module scripts', cabinet.includes('type="module"') && cabinet.includes('src/main.js') && cabinet.includes('src/business_context_autofill.js')],
  ['data module import', js.includes("from './data.js'")],
  ['shared api module', coreApi.includes('export async function apiFetch') && coreApi.includes('export async function postJson')],
  ['shared id module', coreIds.includes('export function createClientId') && coreIds.includes('export function normalizeId')],
  ['shared session api module', coreSessionApi.includes('requestEmailCode') && coreSessionApi.includes('verifyEmailCode')],
  ['shared storage module', coreStorage.includes('export function scopedStorageKey') && coreStorage.includes('export function saveSession')],
  ['shared format module', coreFormat.includes('export function formatNumber') && coreFormat.includes('export function formatMoney')],
  ['business autofill core import', businessAutofill.includes("from './core/api.js'") && businessAutofill.includes('apiFetch')],
  ['standalone login auth', loginJs.includes("from './core/api.js'") && loginJs.includes("from './core/storage.js'")],
  ['email auth view', js.includes('renderLogin') && js.includes('/auth/email/request-code')],
  ['cabinet view', js.includes('renderDashboard')],
  ['audit view', js.includes('renderAudit')],
  ['recommendations view', js.includes('renderRecommendations')],
  ['responsive styles', css.includes('@media')],
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

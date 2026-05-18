import { access, readFile } from 'node:fs/promises';

const requiredFiles = ['index.html', 'login.html', 'app.html', 'src/styles.css', 'src/main.js', 'src/data.js'];

await Promise.all(requiredFiles.map((file) => access(file)));

const html = await readFile('index.html', 'utf8');
const login = await readFile('login.html', 'utf8');
const cabinet = await readFile('app.html', 'utf8');
const css = await readFile('src/styles.css', 'utf8');
const js = await readFile('src/main.js', 'utf8');
const data = await readFile('src/data.js', 'utf8');

const checks = [
  ['root mount point', html.includes('id="app"')],
  ['login page', login.includes('data-page="login"')],
  ['cabinet page', cabinet.includes('data-page="app"')],
  ['stylesheet link', html.includes('src/styles.css')],
  ['script link', html.includes('src/main.js')],
  ['data module import', js.includes("from './data.js'")],
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

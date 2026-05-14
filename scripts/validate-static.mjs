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
  ['single demo project', data.includes('fgrf.ru — демо-проект')],
  ['autopilot rules', data.includes('autopilotRules')],
  ['integrations view', js.includes('renderIntegrations') && js.includes('data-integration="yandex-direct"')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

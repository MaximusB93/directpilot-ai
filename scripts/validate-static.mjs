import { access, readFile } from 'node:fs/promises';

const requiredFiles = ['index.html', 'src/styles.css', 'src/main.js'];

await Promise.all(requiredFiles.map((file) => access(file)));

const html = await readFile('index.html', 'utf8');
const css = await readFile('src/styles.css', 'utf8');
const js = await readFile('src/main.js', 'utf8');

const checks = [
  ['root mount point', html.includes('id="app"')],
  ['stylesheet link', html.includes('src/styles.css')],
  ['script link', html.includes('src/main.js')],
  ['responsive styles', css.includes('@media')],
  ['dashboard data', js.includes('recommendations')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length > 0) {
  console.error(`Static validation failed: ${failed.map(([name]) => name).join(', ')}`);
  process.exit(1);
}

console.log('Static UI validation passed.');

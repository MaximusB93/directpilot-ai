import { cp, mkdir, rm } from 'node:fs/promises';

const sourceRoot = '..';
const outputDirectory = 'public';

await rm(outputDirectory, { recursive: true, force: true });
await mkdir(outputDirectory, { recursive: true });

await Promise.all([
  ...['index.html', 'login.html', 'app.html', 'favicon.svg', '.nojekyll']
    .map((file) => cp(`${sourceRoot}/${file}`, `${outputDirectory}/${file}`)),
  cp(`${sourceRoot}/src`, `${outputDirectory}/src`, { recursive: true }),
]);

console.log(`Prepared ${outputDirectory}/ for the DirectPilot AI frontend Preview.`);

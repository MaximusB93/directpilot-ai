import { cp, mkdir, rm } from 'node:fs/promises';

// The Vercel project has Root Directory = backend. Git still checks out the
// complete repository, so the static MVP frontend is available one level up.
const sourceRoot = '..';
const outputDirectory = 'public';

await rm(outputDirectory, { recursive: true, force: true });
await mkdir(outputDirectory, { recursive: true });

await Promise.all([
  ...['index.html', 'login.html', 'app.html', 'favicon.svg', '.nojekyll']
    .map((file) => cp(`${sourceRoot}/${file}`, `${outputDirectory}/${file}`)),
  cp(`${sourceRoot}/src`, `${outputDirectory}/src`, { recursive: true }),
]);

console.log(`Prepared ${outputDirectory}/ from the repository frontend.`);

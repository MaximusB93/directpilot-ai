import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';

const sourceRoot = '..';
const outputDirectory = 'public';

await rm(outputDirectory, { recursive: true, force: true });
await mkdir(outputDirectory, { recursive: true });

await Promise.all([
  ...['index.html', 'login.html', 'app.html', 'favicon.svg', '.nojekyll']
    .map((file) => cp(`${sourceRoot}/${file}`, `${outputDirectory}/${file}`)),
  // Vercel reserves a top-level `src` directory for build-time source files.
  // Publish browser assets under `assets` so module requests remain static files.
  cp(`${sourceRoot}/src`, `${outputDirectory}/assets`, { recursive: true }),
]);

await Promise.all(
  ['index.html', 'login.html', 'app.html'].map(async (file) => {
    const destination = `${outputDirectory}/${file}`;
    const html = await readFile(destination, 'utf8');
    await writeFile(destination, html.replaceAll('src/', 'assets/'));
  }),
);

console.log(`Prepared ${outputDirectory}/ for the DirectPilot AI frontend Preview.`);

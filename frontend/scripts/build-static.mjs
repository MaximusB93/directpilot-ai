import { access, cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';

const repositorySourceRoot = '..';
const outputDirectory = 'public';

const hasRepositorySource = await access(`${repositorySourceRoot}/src`)
  .then(() => true)
  .catch(() => false);

if (hasRepositorySource) {
  await rm(outputDirectory, { recursive: true, force: true });
  await mkdir(outputDirectory, { recursive: true });

  await Promise.all([
    ...['index.html', 'login.html', 'app.html', 'favicon.svg', '.nojekyll']
      .map((file) => cp(`${repositorySourceRoot}/${file}`, `${outputDirectory}/${file}`)),
    // Vercel reserves a top-level `src` directory for build-time source files.
    // Publish browser assets under `assets` so module requests remain static files.
    cp(`${repositorySourceRoot}/src`, `${outputDirectory}/assets`, { recursive: true }),
  ]);

  await Promise.all(
    ['index.html', 'login.html', 'app.html'].map(async (file) => {
      const destination = `${outputDirectory}/${file}`;
      const html = await readFile(destination, 'utf8');
      await writeFile(destination, html.replaceAll('src/', 'assets/'));
    }),
  );
} else {
  await access(`${outputDirectory}/assets/main.js`);
  console.log('Using prebuilt frontend assets because repository sources are unavailable.');
}

console.log(`Prepared ${outputDirectory}/ for the DirectPilot AI frontend Preview.`);

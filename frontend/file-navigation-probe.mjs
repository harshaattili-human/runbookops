// Isolate file navigation from application code when diagnosing an engine failure.
import { webkit } from '@playwright/test';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const directory = await mkdtemp(join(tmpdir(), 'runbookops-file-'));
const browser = await webkit.launch();
try {
  const path = join(directory, 'control.html');
  await writeFile(path, '<!doctype html><title>File control</title><p>No scripts or assets</p>');
  for (const offline of [true, false]) {
    const context = await browser.newContext({ offline, serviceWorkers: 'block' });
    await context.route(/^https?:/, (route) => route.abort());
    const page = await context.newPage();
    try {
      await page.goto(pathToFileURL(path).href);
      console.log(JSON.stringify({ browser: browser.version(), offline, title: await page.title() }));
    } catch (error) {
      console.log(JSON.stringify({ browser: browser.version(), offline, error: error.message }));
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
  await rm(directory, { recursive: true });
}

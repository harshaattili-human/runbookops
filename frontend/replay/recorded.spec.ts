import { expect, test } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const artifact = resolve('../artifacts/RunbookOps-Demo.html');
const receipt = JSON.parse(readFileSync(artifact.replace(/\.html$/, '.json'), 'utf8'));

test.beforeEach(async ({ context }) => {
  // Apply this to both workflows, including WebKit where offline file navigation fails.
  await context.route(/^https?:/, (route) => route.abort());
});

test('recorded workflow works from a local file without HTTP requests', async ({ page, browser }, info) => {
  console.log(`${info.project.use.browserName} ${browser.version()} / ${info.project.name}`);
  const network: string[] = [];
  const errors: string[] = [];
  page.on('request', (request) => {
    if (/^https?:/.test(request.url())) network.push(request.url());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  expect(createHash('sha256').update(readFileSync(artifact)).digest('hex')).toBe(receipt.html_sha256);
  expect(receipt.scenario_count).toBe(5);
  expect(receipt.document_count).toBe(10);
  await page.goto(pathToFileURL(artifact).href);
  await expect(page.getByText('Recorded demo', { exact: true })).toBeVisible();
  await expect(page.getByText('Interactive replay of actual API results.', { exact: false })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Incident description' })).toHaveAttribute('readonly', '');
  await expect(page.getByRole('checkbox')).toBeDisabled();

  for (const label of ['Connection pool', 'Consumer backlog', 'Stalled approval',
    'Missing information', 'Outside the corpus']) {
    await page.getByRole('button', { name: label, exact: true }).click();
    const supported = ['Connection pool', 'Consumer backlog', 'Stalled approval'].includes(label);
    await expect(page.getByRole('heading', {
      name: supported ? 'Suggested investigation' : 'More context needed',
    })).toBeVisible();
    if (!supported) await expect(page.locator('.source-card')).toHaveCount(0);
    await expect.poll(() => page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  }

  await page.getByRole('button', { name: 'Connection pool', exact: true }).click();
  const card = page.locator('.source-card').first();
  await card.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Close source' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('region', { name: 'Runbook source text' })).toBeFocused();
  await page.evaluate(() => document.fonts.ready);
  await info.attach('recorded-source', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await page.keyboard.press('Escape');
  await expect(card).toBeFocused();

  await page.getByRole('button', { name: /Runbook library/ }).click();
  await page.getByRole('textbox', { name: 'Filter runbooks' }).fill('connection pool');
  await expect(page.locator('.library-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Evaluation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Evaluation results' })).toBeVisible();
  expect(errors).toEqual([]);
  expect(network).toEqual([]);
});

test('recorded sources enforce hashes and unsupported requests stay explicit', async ({ page }) => {
  const network: string[] = [];
  page.on('request', (request) => {
    if (/^https?:/.test(request.url())) network.push(request.url());
  });
  await page.goto(pathToFileURL(artifact).href);
  const result = await page.evaluate(async ({ hashes, query }) => {
    const statuses: number[] = [];
    for (const [slug, hash] of Object.entries(hashes)) {
      const path = '/api/runbooks/' + slug;
      const response = await fetch(path + '?expected_hash=' + hash);
      const body = await response.json();
      if (body.content_hash !== hash) throw new Error('Source hash differs');
      const bytes = new TextEncoder().encode(body.content);
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
        .map((byte) => byte.toString(16).padStart(2, '0')).join('');
      if (digest !== hash) throw new Error('Source content differs');
      statuses.push(response.status);
      const conflict = await fetch(path + '?expected_hash=');
      if ('content' in await conflict.json()) throw new Error('Conflict returned source');
      statuses.push(conflict.status);
    }
    statuses.push((await fetch('/api/runbooks/removed')).status);
    statuses.push((await fetch('/api/triage', { method: 'POST', body: JSON.stringify({ query: 'unrecorded' }) })).status);
    statuses.push((await fetch('/api/triage', { method: 'POST', body: JSON.stringify({ query, use_llm: true }) })).status);
    return statuses;
  }, { hashes: receipt.document_hashes as Record<string, string>, query: receipt.scenarios[0].query });
  expect(result).toEqual([...Array.from({ length: 10 }, () => [200, 409]).flat(), 404, 404, 422]);
  expect(network).toEqual([]);
});

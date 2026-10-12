import { expect, test, type Page, type TestInfo } from '@playwright/test';

async function fitsViewport(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    )
    .toBeLessThanOrEqual(1);
}

async function snapshot(page: Page, info: TestInfo, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await info.attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'No analysis yet' })).toBeVisible();
});

test('live analysis opens its indexed source and supports keyboard reading', async ({
  page,
  browser,
}, info) => {
  console.log(`Chromium ${browser.version()} / ${info.project.name}`);
  const analysis = page.waitForResponse('/api/triage');
  await page.getByRole('button', { name: 'Connection pool', exact: true }).click();
  const result = await (await analysis).json();
  expect(result.mode).toBe('extractive');
  await expect(page.getByRole('heading', { name: 'Suggested investigation' })).toBeVisible();
  await fitsViewport(page);
  await snapshot(page, info, 'live-analysis');

  const card = page.locator('.source-card').first();
  await card.focus();
  const sourceResponse = page.waitForResponse((response) =>
    response.url().includes('/api/runbooks/'),
  );
  await page.keyboard.press('Enter');
  const response = await sourceResponse;
  expect(new URL(response.url()).searchParams.get('expected_hash')).toBe(
    result.sources[0].document_hash,
  );
  const source = await response.json();
  expect(source.content_hash).toBe(result.sources[0].document_hash);
  const dialog = page.getByRole('dialog');
  const close = dialog.getByRole('button', { name: 'Close source' });
  await expect(close).toBeFocused();
  await expect(page.locator('main')).toHaveAttribute('inert', '');
  await fitsViewport(page);
  await snapshot(page, info, 'indexed-source');

  // A long document needs a keyboard-reachable scroll area inside the modal.
  await page.keyboard.press('Tab');
  const lines = page.getByRole('region', { name: 'Runbook source text' });
  await expect(lines).toBeFocused();
  await page.keyboard.press('End');
  await expect.poll(() => lines.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await page.keyboard.press('Tab');
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(lines).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(card).toBeFocused();
  await expect(page.locator('main')).not.toHaveAttribute('inert');
});

test('abstention, library filtering and evaluation remain usable at each width', async ({
  page,
}, info) => {
  await page.getByRole('button', { name: 'Outside the corpus', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'More context needed' })).toBeVisible();
  await expect(page.locator('.source-card')).toHaveCount(0);
  await fitsViewport(page);
  const library = page.getByRole('button', { name: /Runbook library/ });
  await library.focus();
  await page.keyboard.press('Enter');
  await page.getByRole('textbox', { name: 'Filter runbooks' }).fill('connection pool');
  await expect(page.locator('.library-card')).toHaveCount(1);
  await fitsViewport(page);
  await snapshot(page, info, 'filtered-library');
  const evaluation = page.getByRole('button', { name: 'Evaluation', exact: true });
  await evaluation.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Evaluation results' })).toBeVisible();
  await fitsViewport(page);
});

test('a source version conflict preserves focus and reanalysis clears the alert', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'Connection pool', exact: true }).click();
  const card = page.locator('.source-card').first();
  await expect(card).toBeVisible();
  // Fault injection only: successful analysis and the later recovery use the live API.
  await page.route('**/api/runbooks/*', (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Runbook version changed' }),
    }),
  );
  await card.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('changed since the analysis');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(card).toBeFocused();
  await page.unroute('**/api/runbooks/*');
  await page.getByRole('button', { name: 'Connection pool', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.locator('.source-card').first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
});

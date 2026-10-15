import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './replay',
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-replay-report' }]],
  use: {
    browserName: 'chromium',
    offline: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'narrow', use: { viewport: { width: 390, height: 844 } } },
    { name: 'small', use: { viewport: { width: 320, height: 640 } } },
  ],
  // Intentionally no webServer: the artifact must open directly from disk.
});

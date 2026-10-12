import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    browserName: 'chromium',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'narrow', use: { viewport: { width: 390, height: 844 } } },
    { name: 'small', use: { viewport: { width: 320, height: 640 } } },
  ],
  webServer: {
    command: 'python -m uvicorn runbookops.api:app --host 127.0.0.1 --port 8765',
    cwd: '..',
    url: 'http://127.0.0.1:8765/healthz',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

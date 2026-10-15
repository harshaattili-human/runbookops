import { defineConfig } from '@playwright/test';
import { browserProjects } from './browser-projects';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: browserProjects,
  webServer: {
    command: 'python -m uvicorn runbookops.api:app --host 127.0.0.1 --port 8765',
    cwd: '..',
    url: 'http://127.0.0.1:8765/healthz',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

import { defineConfig } from '@playwright/test';
import { browserProjects } from './browser-projects';

export default defineConfig({
  testDir: './replay',
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-replay-report' }]],
  use: {
    offline: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: browserProjects,
  // Intentionally no webServer: the artifact must open directly from disk.
});

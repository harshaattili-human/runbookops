import { defineConfig } from '@playwright/test';
import { browserProjects } from './browser-projects';

export default defineConfig({
  testDir: './replay',
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-replay-report' }]],
  use: {
    offline: true,
    serviceWorkers: 'block',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  // WebKit's offline setting rejects file navigation itself; HTTP(S) is blocked in the suite.
  projects: browserProjects.map((project) => ({ ...project,
    use: { ...project.use, offline: project.use.browserName !== 'webkit' },
  })),
  // Intentionally no webServer: the artifact must open directly from disk.
});

// Use identical viewports for live and file-replay checks across the three engines.
export const browserProjects = (['chromium', 'firefox', 'webkit'] as const).flatMap(
  (browserName) => [
    { name: 'desktop', viewport: { width: 1440, height: 900 } },
    { name: 'narrow', viewport: { width: 390, height: 844 } },
    { name: 'small', viewport: { width: 320, height: 640 } },
  ].map(({ name, viewport }) => ({ name: `${browserName}-${name}`, use: { browserName, viewport } })),
);

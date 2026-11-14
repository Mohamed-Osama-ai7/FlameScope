import { defineConfig, type PlaywrightTestProject } from '@playwright/test';

// E2E_BROWSERS selects engines (default: system Chrome only). Engines: chromium (system Chrome),
// msedge (system Edge, another Chromium build), firefox, webkit (Playwright-managed builds).
const engines = (process.env.E2E_BROWSERS ?? 'chromium').split(',');
const projects: PlaywrightTestProject[] = engines.map((name) => {
  if (name === 'chromium') return { name, use: { channel: 'chrome' } };
  if (name === 'msedge') return { name, use: { channel: 'msedge' } };
  return { name, use: { browserName: name as 'firefox' | 'webkit' } };
});

// The production build is served by `vite preview` on port 4180.
export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 90_000,
  expect: { timeout: 15_000, toHaveScreenshot: { maxDiffPixelRatio: 0.02 } },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4180',
    headless: true,
    viewport: { width: 1440, height: 900 },
    contextOptions: { reducedMotion: 'reduce' },
    trace: 'off',
  },
  projects,
  webServer: {
    command: 'npx vite preview --port 4180 --strictPort --host 127.0.0.1',
    url: 'http://127.0.0.1:4180',
    reuseExistingServer: true,
    timeout: 60_000,
  },
  // Baselines are per engine: a Firefox render must never be compared with a Chromium baseline.
  snapshotPathTemplate: '{testDir}/__screenshots__/{testFilePath}/{projectName}/{arg}{ext}',
});

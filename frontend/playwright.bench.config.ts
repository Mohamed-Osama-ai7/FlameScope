import { defineConfig } from '@playwright/test';

// Browser benchmarks (not part of the default test run). BENCH_BROWSERS=chromium,firefox,webkit selects engines.
const engines = (process.env.BENCH_BROWSERS ?? 'chromium').split(',');
const projects = engines.map((name) =>
  name === 'chromium'
    ? { name, use: { channel: 'chrome', launchOptions: { args: ['--enable-precise-memory-info', '--js-flags=--expose-gc'] } } }
    : { name, use: { browserName: name as 'firefox' | 'webkit' } },
);

export default defineConfig({
  testDir: 'tests/bench',
  testMatch: '**/*.bench.ts',
  timeout: 300_000,
  globalTimeout: 1_500_000, // strict wall-clock limit for the whole benchmark run (25 min)
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  use: { headless: true, viewport: { width: 1280, height: 900 }, contextOptions: { reducedMotion: 'reduce' } },
  projects,
  webServer: [
    {
      // SYNTHETIC render harness (never part of the app build)
      command: 'npx vite build --config vite.bench.config.ts && npx vite preview --config vite.bench.config.ts',
      url: 'http://127.0.0.1:4190',
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      // Production build of the real application (real FLEX data)
      command: 'npx vite build && npx vite preview --port 4180 --strictPort --host 127.0.0.1', // same bundle as `npm run build` (which only adds the type check)
      url: 'http://127.0.0.1:4180',
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});

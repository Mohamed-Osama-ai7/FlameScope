import { test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stat } from './stats';

/**
 * REAL FLEX data (274 records) in the production app build, timed in-page with performance.now().
 * Warm-up runs are discarded; median and p95 (nearest rank) are reported over the repetitions.
 */
const HERE = dirname(fileURLToPath(import.meta.url));
const LABEL = process.env.BENCH_LABEL ?? 'unlabelled';
const APP = 'http://127.0.0.1:4180';
const WARMUP = 3;
const COLD_RUNS = 10;
const REPS = 20;
const EXPORT_REPS = 10;

type W = Window & { __tShell?: number; __tChart?: number; gc?: () => void };
const results: Record<string, unknown> = { label: LABEL, dataset: 'real FLEX PSI-69 v0.2.0 (274 records)', warmup: WARMUP, coldRuns: COLD_RUNS, reps: REPS, exportReps: EXPORT_REPS };

test.afterAll(() => {
  const dir = join(HERE, '__results__');
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `app-${LABEL}-${process.env.BENCH_BROWSERS ?? 'chromium'}.json`);
  writeFileSync(file, JSON.stringify(results, null, 2));
  console.log(`[bench] wrote ${file}`);
});

test('cold load of the Combustion Explorer (fresh context, empty cache)', async ({ browser, browserName }) => {
  test.setTimeout(600_000);
  const shell: number[] = [], chart: number[] = [], dcl: number[] = [], fcp: number[] = [];
  let transferKB = 0, plotlyKB = 0;
  for (let i = -1; i < COLD_RUNS; i++) {
    const ctx = await browser.newContext({ reducedMotion: 'reduce', viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    await page.addInitScript(() => {
      const w = window as W;
      new MutationObserver(() => {
        if (w.__tShell === undefined && document.querySelector('.tiles, .card-head h3')) w.__tShell = performance.now();
        if (w.__tChart === undefined && document.querySelector('.js-plotly-plot .scatterlayer .point')) w.__tChart = performance.now();
      }).observe(document, { childList: true, subtree: true });
    });
    await page.goto(`${APP}/#combustion`);
    await page.waitForFunction(() => (window as W).__tChart !== undefined, undefined, { timeout: 60_000 });
    const m = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
      const res = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
      const paint = performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null;
      return {
        shell: (window as W).__tShell ?? 0, chart: (window as W).__tChart ?? 0, dcl: nav.domContentLoadedEventEnd, fcp: paint,
        transferKB: res.reduce((a, r) => a + r.transferSize, 0) / 1024,
        plotlyKB: (res.find((r) => /plotly/.test(r.name))?.encodedBodySize ?? 0) / 1024,
      };
    });
    if (i >= 0) { shell.push(m.shell); chart.push(m.chart); dcl.push(m.dcl); if (m.fcp !== null) fcp.push(m.fcp); transferKB = Math.round(m.transferKB); plotlyKB = Math.round(m.plotlyKB); }
    await ctx.close();
  }
  results.coldLoad = { browser: browserName, shellMs: stat(shell), firstChartDrawnMs: stat(chart), domContentLoadedMs: stat(dcl), firstContentfulPaintMs: fcp.length ? stat(fcp) : 'unavailable', resourcesTransferredKB: transferKB, plotlyChunkKB: plotlyKB };
  console.log(`[bench] cold ${JSON.stringify(results.coldLoad)}`);
});

test('interactions on real data: view switch, filter toggle, selection to inspector, heap', async ({ page, browserName }) => {
  test.setTimeout(600_000);
  await page.goto(`${APP}/#combustion`);
  await page.waitForFunction(() => !!document.querySelector('.js-plotly-plot .scatterlayer .point'), undefined, { timeout: 60_000 });
  await page.evaluate(() => {
    // Timing helpers live in the page so no protocol latency enters the measurements.
    const w = window as unknown as Record<string, unknown>;
    w.__untilAfterplot = (action: () => void) =>
      new Promise<number>((resolve) => {
        const gd = document.querySelector('.js-plotly-plot') as unknown as { once: (e: string, f: () => void) => void };
        const t0 = performance.now();
        gd.once('plotly_afterplot', () => requestAnimationFrame(() => resolve(performance.now() - t0)));
        action();
      });
    w.__untilSelector = (action: () => void, selector: string, present: boolean) =>
      new Promise<number>((resolve) => {
        const t0 = performance.now();
        const check = () => (!!document.querySelector(selector) === present ? (obs.disconnect(), resolve(performance.now() - t0), true) : false);
        const obs = new MutationObserver(check);
        obs.observe(document.body, { childList: true, subtree: true });
        action();
        check();
      });
  });
  const radio = (name: string) => `Array.from(document.querySelectorAll('[role=radio]')).find(b => b.textContent.trim() === ${JSON.stringify(name)})`;
  const timeSwitch = (name: string) => page.evaluate(`window.__untilAfterplot(() => ${radio(name)}.click())`) as Promise<number>;
  const timeFilter = () => page.evaluate(`window.__untilAfterplot(() => document.getElementById('f-fuels-Heptane').click())`) as Promise<number>;
  const timeSelect = () => page.evaluate(async () => {
    const w = window as unknown as { __untilSelector: (a: () => void, s: string, p: boolean) => Promise<number> };
    const gd = document.querySelector('.js-plotly-plot') as unknown as { data: { customdata?: string[] }[]; emit: (e: string, d: unknown) => void };
    const key = gd.data.find((d) => d.customdata?.length)!.customdata![0];
    const open = await w.__untilSelector(() => gd.emit('plotly_click', { points: [{ customdata: key }] }), '[role=dialog]', true);
    const close = await w.__untilSelector(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })), '[role=dialog]', false);
    return { open, close };
  });
  const heap = () => page.evaluate(() => { (window as W).gc?.(); const m = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory; return m ? m.usedJSHeapSize / 1048576 : null; });

  for (let i = 0; i < WARMUP; i++) { await timeSwitch('K vs D₀'); await timeSwitch('K vs O₂'); await timeFilter(); await timeFilter(); await timeSelect(); }
  const heapBefore = await heap();
  const sw: number[] = [], fl: number[] = [], op: number[] = [], cl: number[] = [];
  for (let i = 0; i < REPS; i++) {
    sw.push(await timeSwitch('K vs D₀')); sw.push(await timeSwitch('K vs O₂'));
    fl.push(await timeFilter()); fl.push(await timeFilter());
    const s = await timeSelect(); op.push(s.open); cl.push(s.close);
  }
  const heapAfter = await heap();
  results.interactions = {
    browser: browserName,
    viewSwitchToChartMs: stat(sw), filterToggleToChartMs: stat(fl), selectionToInspectorOpenMs: stat(op), inspectorCloseMs: stat(cl),
    heapMBBefore: heapBefore === null ? 'unavailable' : Math.round(heapBefore * 10) / 10,
    heapMBAfterRepetitions: heapAfter === null ? 'unavailable' : Math.round(heapAfter * 10) / 10,
    note: 'selection is dispatched as the Plotly plotly_click event the real handler listens to (same code path as a mouse click, without pointer-event latency)',
  };
  console.log(`[bench] interactions ${JSON.stringify(results.interactions)}`);
});

/**
 * Chrome holds the 11th consecutive automatic download from one tab for a permission prompt that headless Chrome
 * cannot answer (found while benchmarking). So each tab performs at most 5 downloads and every wait has a hard timeout.
 */
async function timedDownloads(
  context: import('@playwright/test').BrowserContext,
  open: (p: import('@playwright/test').Page) => Promise<void>,
  trigger: (p: import('@playwright/test').Page) => Promise<unknown>,
  reps: number,
) {
  const times: number[] = [];
  let page = await context.newPage();
  await open(page);
  let used = 0;
  for (let i = -WARMUP; i < reps; i++) {
    if (used >= 5) {
      await page.close();
      page = await context.newPage();
      await open(page);
      used = 0;
    }
    const t = Date.now();
    await Promise.all([page.waitForEvent('download', { timeout: 30_000 }), trigger(page)]);
    used += 1;
    if (i >= 0) times.push(Date.now() - t);
  }
  await page.close();
  return times;
}

test('exports on real data (end-to-end incl. Playwright download handling)', async ({ browser, browserName }) => {
  test.setTimeout(300_000);
  const context = await browser.newContext({ acceptDownloads: true, reducedMotion: 'reduce', viewport: { width: 1440, height: 900 } });
  const openTable = async (p: import('@playwright/test').Page) => {
    await p.goto(`${APP}/#observations`);
    await p.getByTestId('record-table').waitFor({ timeout: 30_000 });
  };
  const openChart = async (p: import('@playwright/test').Page) => {
    await p.goto(`${APP}/#combustion`);
    await p.waitForFunction(() => !!document.querySelector('.js-plotly-plot .scatterlayer .point'), undefined, { timeout: 30_000 });
  };
  const csv = await timedDownloads(context, openTable, (p) => p.getByRole('button', { name: /Export CSV/ }).click(), EXPORT_REPS);
  const svg = await timedDownloads(context, openChart, (p) => p.locator('[data-view="k_o2"]').getByRole('button', { name: 'Export SVG' }).click(), EXPORT_REPS);
  const png = await timedDownloads(context, openChart, (p) => p.locator('[data-view="k_o2"]').getByRole('button', { name: 'Export PNG' }).click(), EXPORT_REPS);
  await context.close();
  results.exports = { browser: browserName, csvMs: stat(csv), svgMs: stat(svg), pngMs: stat(png), note: 'click to download event; includes Playwright overhead; at most 5 downloads per tab (Chrome throttles automatic downloads)' };
  console.log(`[bench] exports ${JSON.stringify(results.exports)}`);
});

import { expect, test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { firstPointPosition, openLab, waitForPlot } from './helpers';

/** Benchmarks on the REAL 274-record dataset in Chrome. Ceilings are generous; they catch regressions only. */
const HERE = dirname(fileURLToPath(import.meta.url));
const results: Record<string, number | string> = {};

test.afterAll(() => {
  const dir = join(HERE, '__benchmarks__');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'latest.json'), JSON.stringify({ note: 'machine-specific timings; real 274-record dataset, SVG traces', ...results }, null, 2));
  console.log('[bench]', JSON.stringify(results));
});

test('load: dataset fetch, first paint and chart readiness', async ({ page }) => {
  const t0 = Date.now();
  await openLab(page, 'combustion');
  await page.getByRole('heading', { name: /Reported K vs O₂/ }).waitFor();
  results.shell_ready_ms = Date.now() - t0;
  const t1 = Date.now();
  await waitForPlot(page);
  results.first_chart_drawn_after_shell_ms = Date.now() - t1;
  const nav = await page.evaluate(() => {
    const n = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    const res = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
    return {
      domContentLoaded: Math.round(n.domContentLoadedEventEnd),
      transferKB: Math.round(res.reduce((a, r) => a + r.transferSize, 0) / 1024),
      plotlyKB: Math.round((res.find((r) => r.name.includes('plotly'))?.encodedBodySize ?? 0) / 1024),
      datasetKB: Math.round((res.find((r) => r.name.includes('flex_lab_dataset'))?.encodedBodySize ?? 0) / 1024),
    };
  });
  Object.assign(results, { dom_content_loaded_ms: nav.domContentLoaded, resources_transferred_kb: nav.transferKB, plotly_chunk_kb: nav.plotlyKB, dataset_kb: nav.datasetKB });
  expect(results.shell_ready_ms as number).toBeLessThan(10_000);
});

test('filtering and view switching latency', async ({ page }) => {
  await openLab(page, 'combustion');
  await waitForPlot(page);
  const samples: number[] = [];
  for (const n of ['Heptane', 'Heptane', 'Fiber, translated', 'Fiber, translated']) {
    const t0 = Date.now();
    await page.getByLabel(n).first().click();
    await page.waitForTimeout(50);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    samples.push(Date.now() - t0);
  }
  results.filter_toggle_to_painted_ms_median_incl_50ms_wait = samples.sort((a, b) => a - b)[Math.floor(samples.length / 2)];
  const t = Date.now();
  await page.getByRole('radio', { name: 'K vs D₀' }).click();
  await page.locator('[data-view="k_d0"]').waitFor();
  await waitForPlot(page);
  results.view_switch_to_chart_ms = Date.now() - t;
  expect(results.view_switch_to_chart_ms as number).toBeLessThan(5_000);
});

test('selection to inspector latency and JS heap', async ({ page }) => {
  await openLab(page, 'combustion');
  await waitForPlot(page);
  const p = await firstPointPosition(page);
  const t = Date.now();
  await page.mouse.click(p.x, p.y);
  await page.getByRole('dialog').waitFor();
  results.click_to_inspector_ms = Date.now() - t;
  const heap = await page.evaluate(() => (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? null);
  results.js_heap_mb_with_chart_open = heap === null ? 'unavailable' : Math.round(heap / 1048576);
  expect(results.click_to_inspector_ms as number).toBeLessThan(3_000);
});

test('export latency (CSV, SVG, PNG)', async ({ page }) => {
  await openLab(page, 'observations');
  const csv = Date.now();
  await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Export CSV/ }).click()]);
  results.csv_export_ms = Date.now() - csv;
  await page.getByRole('link', { name: 'Combustion Explorer' }).click();
  await waitForPlot(page);
  const card = page.locator('[data-view="k_o2"]');
  for (const fmt of ['SVG', 'PNG']) {
    const t = Date.now();
    await Promise.all([page.waitForEvent('download', { timeout: 60_000 }), card.getByRole('button', { name: `Export ${fmt}` }).click()]);
    results[`${fmt.toLowerCase()}_export_ms`] = Date.now() - t;
  }
  expect(results.png_export_ms as number).toBeLessThan(20_000);
});

test('table sorting and search stay responsive with all 274 records', async ({ page }) => {
  await openLab(page, 'observations');
  await page.getByLabel('Fiber, translated').check();
  await page.getByLabel('Fiber, translation not stated').check();
  await page.getByLabel('Conflicting sources').check();
  await expect(page.getByTestId('record-table').locator('tbody tr')).toHaveCount(274);
  const t = Date.now();
  await page.getByRole('button', { name: /Reported K/ }).click();
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  results.table_sort_274_rows_ms = Date.now() - t;
  const s = Date.now();
  await page.getByLabel('Search records').fill('193F001');
  await expect(page.getByTestId('record-table').locator('tbody tr')).toHaveCount(2);
  results.table_search_ms = Date.now() - s;
  expect(results.table_sort_274_rows_ms as number).toBeLessThan(2_000);
});

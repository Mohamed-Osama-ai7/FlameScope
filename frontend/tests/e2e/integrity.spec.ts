import { expect, test } from '@playwright/test';
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openLab, waitForPlot } from './helpers';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', '..', '..', 'docs', 'screenshots', 'lab', 'exports');
const SECTIONS = ['overview', 'combustion', 'conditions', 'outcomes', 'quality', 'observations'];

test('duplicate source identifier 193F001 stays two distinct records end to end', async ({ page }) => {
  await openLab(page, 'observations');
  for (const mode of ['Fiber, translated', 'Fiber, translation not stated', 'Conflicting sources']) await page.getByLabel(mode).check();
  await page.getByLabel('Search records').fill('193F001');
  const rows = page.getByTestId('record-table').locator('tbody tr');
  await expect(rows).toHaveCount(2);
  const keys = await rows.evaluateAll((trs) => trs.map((tr) => tr.getAttribute('data-record-key')));
  expect(new Set(keys).size).toBe(2);
  expect(keys.join()).toContain('FLEX-070');
  expect(keys.join()).toContain('FLEX-073');
  for (const key of keys as string[]) {
    await page.getByRole('button', { name: `Inspect ${key}` }).click();
    await expect(page.getByTestId('inspector-key')).toHaveText(key);
    await expect(page.getByRole('dialog')).toContainText('duplicate identifier in source');
    await page.keyboard.press('Escape');
  }
  // The data-quality section lists both records under the duplicate-identifier rule.
  await page.getByRole('link', { name: 'Data Quality & Evidence' }).click();
  const item = page.getByTestId('warning-list').locator('li', { hasText: 'duplicate source identifier' });
  await expect(item.getByRole('button')).toHaveCount(2);
});

test('SVG/PNG exports are intact: point count equals the plotted records and the config JSON', async ({ page }) => {
  await openLab(page, 'combustion');
  await waitForPlot(page);
  const card = page.locator('[data-view="k_o2"]');
  const [cfgDl] = await Promise.all([page.waitForEvent('download'), card.getByRole('button', { name: 'Export config JSON' }).click()]);
  const cfg = JSON.parse(readFileSync((await cfgDl.path())!, 'utf-8'));
  const shown = cfg.counts.shown as number;
  expect(shown).toBe(66);

  const [svgDl] = await Promise.all([page.waitForEvent('download', { timeout: 60_000 }), card.getByRole('button', { name: 'Export SVG' }).click()]);
  const svg = readFileSync((await svgDl.path())!, 'utf-8');
  expect(svg).toContain('<svg');
  expect(svg).not.toContain('Loading chart');
  expect(svg).toContain('Reported burning-rate constant K (mm²/s)');
  expect(svg).toContain('O₂ mole fraction (mole fraction)');
  expect(svg).toContain('Methanol');
  expect(svg).toContain('Heptane');
  const points = (svg.match(/<path class="point(?: [^"]*)?"/g) ?? []).length; // Plotly adds 'plotly-customdata'
  expect(points, 'exported SVG must contain exactly the plotted points').toBe(shown);

  const [pngDl] = await Promise.all([page.waitForEvent('download', { timeout: 60_000 }), card.getByRole('button', { name: 'Export PNG' }).click()]);
  const pngPath = (await pngDl.path())!;
  const png = readFileSync(pngPath);
  expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  const w = png.readUInt32BE(16);
  const h = png.readUInt32BE(20);
  expect(w).toBe(2400); // 1200 px at scale 2
  expect(h).toBeGreaterThanOrEqual(840);
  expect(png.length).toBeGreaterThan(20_000);
  mkdirSync(OUT, { recursive: true });
  const suffix = test.info().project.name === 'chromium' ? '' : `.${test.info().project.name}`;
  copyFileSync(pngPath, join(OUT, `exported-k_o2${suffix}.png`));
  // Render the exported SVG in a fresh page so its appearance can be inspected, not just parsed.
  const view = await page.context().newPage();
  await view.setViewportSize({ width: 1240, height: 560 });
  await view.setContent(`<body style="margin:0;background:#fff">${svg.slice(svg.indexOf('<svg'))}</body>`);
  await view.screenshot({ path: join(OUT, `exported-k_o2-svg-rendered${suffix}.png`) });
  await view.close();
});

test('no console errors or failed requests in any section, both themes', async ({ page }) => {
  const problems: string[] = [];
  page.on('console', (m) => {
    // The header's optional backend /health probe fails when the API is not running; that is expected.
    if (m.type() === 'error' && !/ERR_CONNECTION_REFUSED|Failed to load resource.*(8000|health)|NS_ERROR_CONNECTION_REFUSED|Could not connect/i.test(m.text())) problems.push(`console: ${m.text()}`);
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  for (const theme of ['dark', 'light'] as const) {
    for (const s of SECTIONS) {
      await openLab(page, s, theme);
      if (['combustion', 'conditions', 'outcomes'].includes(s)) await waitForPlot(page);
    }
  }
  expect(problems).toEqual([]);
});

test('chart toolbar offers no cloud-upload or Chart Studio action (Plotly 4 enables Upload to Cloud by default)', async ({ page }) => {
  await openLab(page, 'combustion');
  await waitForPlot(page);
  const titles = await page.locator('.modebar-btn').evaluateAll((els) => els.map((e) => e.getAttribute('data-title') ?? ''));
  expect(titles.length, 'the toolbar must exist so this check is not vacuous').toBeGreaterThan(3);
  expect(titles.some((x) => /zoom|pan|reset/i.test(x))).toBe(true);
  expect(titles.filter((x) => /cloud|upload|chart studio|send|edit in/i.test(x))).toEqual([]);
  const sendButtons = await page.locator('.modebar-btn[data-title*="loud" i], .modebar-btn[data-attr="sendDataToCloud"]').count();
  expect(sendButtons).toBe(0);
});

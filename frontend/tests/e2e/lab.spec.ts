import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { firstPointPosition, openLab, waitForPlot } from './helpers';

test.describe('Scientific Exploration Lab · verified FLEX v0.2.0 data', () => {
  test('overview derives counts from source records and distinguishes records from tests', async ({ page }) => {
    await openLab(page);
    await expect(page.getByRole('heading', { name: /What this dataset contains/ })).toBeVisible();
    await expect(page.locator('.tile', { hasText: 'Records (PSI-69 rows)' })).toContainText('274');
    await expect(page.locator('.tile', { hasText: 'Unique FLEX identifiers' })).toContainText('273');
    await expect(page.locator('.tile', { hasText: 'Tests stated by NASA' })).toContainText('284');
    await expect(page.getByText('Printed rows not in PSI')).toBeVisible();
    await expect(page.getByText('H₂O mole fraction').first().or(page.getByText('UNKNOWN').first())).toBeVisible();
  });

  test('K vs O2 shows per-fuel, per-support panels with N and rules; never pools support modes', async ({ page }) => {
    await openLab(page, 'combustion');
    await waitForPlot(page);
    const card = page.locator('[data-view="k_o2"]');
    await expect(card.getByTestId('chart-k_o2-counts')).toContainText('66 of 94 eligible records (274 total)');
    await expect(card).toContainText('Methanol · Free-floating (n=38)');
    await expect(card).toContainText('Heptane · Free-floating (n=28)');
    await expect(card).not.toContainText('Fiber, translated (n=');
    await expect(card.getByText('Eligibility rule')).toBeVisible();
    await expect(card.getByText('Limitations')).toBeVisible();
  });

  test('selecting a chart point opens the evidence inspector for that exact record', async ({ page }) => {
    await openLab(page, 'combustion');
    await waitForPlot(page);
    const p = await firstPointPosition(page);
    await page.mouse.click(p.x, p.y);
    const dlg = page.getByRole('dialog', { name: /FLEX-/ });
    await expect(dlg).toBeVisible();
    await expect(dlg.getByTestId('inspector-key')).toHaveText(p.key);
    for (const text of ['PSI-69 row', 'NASA FLEX test', 'Original PSI header', 'Raw SHA-256', 'Enrichment SHA-256', 'Source URL', 'NASA test note', 'Burning rate; mm']) {
      await expect(dlg).toContainText(text);
    }
    await expect(dlg).toContainText('37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96');
    await page.keyboard.press('Escape');
    await expect(dlg).toBeHidden();
  });

  test('selection is linked: the observations table highlights the same record', async ({ page }) => {
    await openLab(page, 'combustion');
    await waitForPlot(page);
    const p = await firstPointPosition(page);
    await page.mouse.click(p.x, p.y);
    await page.keyboard.press('Escape');
    await page.getByRole('link', { name: 'Observations', exact: true }).click();
    await expect(page.locator(`tr[data-record-key="${p.key}"]`)).toHaveClass(/is-selected/);
  });

  test('filters update counts consistently and reset restores them', async ({ page }) => {
    await openLab(page, 'combustion');
    await waitForPlot(page);
    const summary = page.getByTestId('filter-summary');
    await expect(summary).toContainText('209 of 274 records pass');
    await page.getByLabel('Heptane', { exact: false }).first().uncheck();
    await expect(summary).toContainText('hidden by fuel');
    const card = page.locator('[data-view="k_o2"]');
    await expect(card.getByTestId('chart-k_o2-counts')).toContainText('38 of 94 eligible');
    await page.getByRole('button', { name: 'Reset filters' }).click();
    await expect(summary).toContainText('209 of 274 records pass');
    await expect(card.getByTestId('chart-k_o2-counts')).toContainText('66 of 94 eligible');
  });

  test('enabling fiber support adds separate panels instead of pooling', async ({ page }) => {
    await openLab(page, 'combustion');
    await waitForPlot(page);
    await page.getByLabel('Fiber, translated').check();
    const card = page.locator('[data-view="k_o2"]');
    await expect(card).toContainText('Fiber, translated (n=');
    await expect(card).toContainText('Methanol · Free-floating (n=38)');
  });

  test('conditions: incomplete composition is disclosed, never normalised', async ({ page }) => {
    await openLab(page, 'conditions');
    await expect(page.getByText('Incomplete composition.')).toBeVisible();
    await expect(page.getByText(/never normalised to 100 %/)).toBeVisible();
    await expect(page.locator('td.unknown', { hasText: 'UNKNOWN' }).first()).toBeVisible();
    await expect(page.getByText(/ternary/i).first()).toBeVisible(); // stated as not drawn
  });

  test('outcomes: null extinction diameters keep distinct NASA semantics', async ({ page }) => {
    await openLab(page, 'outcomes');
    const t = page.getByTestId('dext-origin-table');
    for (const label of ["No finite-size extinction", 'Not listed: insufficient HiBMs', 'Extrapolated (NASA caption)', 'Zero value: meaning unconfirmed', "Conflicting: '–' with test end Extinction"]) {
      await expect(t).toContainText(label);
    }
    await expect(page.getByText(/disruptive extinction of methanol is probably due to needle-coating contamination/)).toBeVisible();
    await expect(page.getByText(/no conclusion can be drawn on heptane disruption/)).toBeVisible();
  });

  test('quality: every warning links to records and a documented rule', async ({ page }) => {
    await openLab(page, 'quality');
    const list = page.getByTestId('warning-list');
    await expect(list).toContainText('rule quality.invalid_nonpositive_pressure');
    const chip = list.getByRole('button', { name: /Inspect PSI69-r114/ }).first();
    await expect(chip).toBeVisible();
    await chip.click();
    await expect(page.getByTestId('inspector-key')).toContainText('FLEX-114');
    await expect(page.getByRole('dialog')).toContainText('Table IX/PSI 0 mmHg vs matrix Table VI 0.7 atm');
  });

  test('exports: CSV preserves IDs, provenance and export type', async ({ page }) => {
    await openLab(page, 'observations');
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /Export CSV/ }).click()]);
    const path = await dl.path();
    const csv = readFileSync(path!, 'utf-8');
    expect(dl.suggestedFilename()).toBe('flamescope_flex_observations_v0.2.0.csv');
    const lines = csv.trim().split('\n');
    expect(lines.length).toBe(1 + 209); // default filter = free-floating
    expect(csv).toContain('PSI69-r');
    expect(csv).toContain('37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96');
    expect(csv).toContain('filtered raw observations (NASA-reported values; no calculation)');
    expect(csv).toContain('mm²/s');
    expect(csv).not.toContain('SYNTH');
  });

  test('exports: analysis summary and provenance JSON', async ({ page }) => {
    await openLab(page, 'observations');
    const [a] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export analysis summary JSON' }).click()]);
    const summary = JSON.parse(readFileSync((await a.path())!, 'utf-8'));
    expect(summary.export_type).toContain('aggregated');
    expect(summary.provenance.raw_sha256).toHaveLength(64);
    expect(summary.filters_at_export.supportModes).toEqual(['free_floating']);
    expect(summary.strata.length).toBe(137);
    const [b] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export provenance JSON' }).click()]);
    const prov = JSON.parse(readFileSync((await b.path())!, 'utf-8'));
    expect(prov.analysis_version).toBe('0.2.0');
    expect(prov.synthetic).toBe(false);
    await expect(page.getByText(/PDF export is not offered/)).toBeVisible();
  });

  test('exports: chart config JSON, SVG and PNG are produced and consistent with the chart', async ({ page }) => {
    await openLab(page, 'combustion');
    await waitForPlot(page);
    const card = page.locator('[data-view="k_o2"]');
    const [c] = await Promise.all([page.waitForEvent('download'), card.getByRole('button', { name: 'Export config JSON' }).click()]);
    const cfg = JSON.parse(readFileSync((await c.path())!, 'utf-8'));
    expect(cfg.view.id).toBe('k_o2');
    expect(cfg.view.units.y).toBe('mm²/s');
    expect(cfg.counts.shown).toBe(66);
    expect(cfg.panels.flatMap((p: { record_keys: string[] }) => p.record_keys)).toHaveLength(66);
    const [s] = await Promise.all([page.waitForEvent('download', { timeout: 60_000 }), card.getByRole('button', { name: 'Export SVG' }).click()]);
    const svg = readFileSync((await s.path())!, 'utf-8');
    expect(s.suggestedFilename()).toBe('flamescope_k_o2_v0.2.0.svg');
    expect(svg.startsWith('<svg') || svg.includes('<svg')).toBe(true);
    const [n] = await Promise.all([page.waitForEvent('download', { timeout: 60_000 }), card.getByRole('button', { name: 'Export PNG' }).click()]);
    const png = readFileSync((await n.path())!);
    expect(n.suggestedFilename()).toBe('flamescope_k_o2_v0.2.0.png');
    expect(png.subarray(1, 4).toString()).toBe('PNG');
    expect(png.length).toBeGreaterThan(10_000);
  });

  test('keyboard: sections, filters and inspector are operable without a mouse', async ({ page }) => {
    await openLab(page);
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
    await page.getByRole('link', { name: 'Observations', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('record-table')).toBeVisible();
    const inspect = page.getByRole('button', { name: /Inspect PSI69-r001/ });
    await inspect.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.locator('#inspector-title')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(inspect).toBeFocused();
  });
});

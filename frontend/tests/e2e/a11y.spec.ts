import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { openLab, waitForPlot } from './helpers';

const SECTIONS = ['overview', 'combustion', 'conditions', 'outcomes', 'quality', 'observations'];
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

async function audit(page: Page, label: string) {
  const res = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const summary = res.violations.map((v) => `${v.id} [${v.impact}] x${v.nodes.length}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
  expect.soft(summary, `axe violations on ${label}`).toEqual([]);
  expect(res.passes.length, `axe must have evaluated rules on ${label}`).toBeGreaterThan(15);
  return res;
}

for (const theme of ['dark', 'light'] as const) {
  test.describe(`axe · ${theme} theme · desktop`, () => {
    for (const s of SECTIONS) {
      test(`section ${s}`, async ({ page }) => {
        await openLab(page, s, theme);
        if (['combustion', 'conditions', 'outcomes'].includes(s)) await waitForPlot(page);
        await audit(page, `${theme}/${s}`);
      });
    }
    test('evidence inspector dialog', async ({ page }) => {
      await openLab(page, 'observations', theme);
      await page.getByRole('button', { name: /Inspect PSI69-r001/ }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await audit(page, `${theme}/inspector`);
    });
  });
}

test.describe('axe · mobile 390px', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  for (const s of ['overview', 'combustion', 'observations']) {
    test(`section ${s}`, async ({ page }) => {
      await openLab(page, s, 'dark');
      if (s === 'combustion') await waitForPlot(page);
      await audit(page, `mobile/${s}`);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, 'page must not scroll horizontally on mobile').toBeLessThanOrEqual(1);
    });
  }
});

test('reduced motion: the preference is active and nothing animates', async ({ page }) => {
  await openLab(page, 'overview');
  // The preference must really be emulated (guards against a silently ignored config option).
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  const longest = await page.evaluate(() =>
    Math.max(0, ...[...document.querySelectorAll('*')].map((e) => parseFloat(getComputedStyle(e).transitionDuration) || 0)),
  );
  expect(longest).toBe(0);
  expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
});

test('focus is visible on interactive controls', async ({ page }) => {
  await openLab(page, 'combustion');
  const btn = page.getByRole('radio', { name: 'K vs pressure' });
  await btn.focus();
  const outline = await btn.evaluate((el) => getComputedStyle(el).outlineStyle + ' ' + getComputedStyle(el).outlineWidth);
  expect(outline).toMatch(/solid 3px/);
});

test.describe('responsive chart geometry', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('mobile: fuel panels stack in one column (no overlapping titles or axes)', async ({ page }) => {
    await openLab(page, 'combustion', 'dark');
    await waitForPlot(page);
    const doms = await page.evaluate(() => {
      const gd = document.querySelector('.js-plotly-plot') as unknown as { _fullLayout: Record<string, { domain?: number[] }> };
      return Object.entries(gd._fullLayout).filter(([k]) => /^xaxis\d*$/.test(k)).map(([, v]) => v.domain);
    });
    expect(doms.length).toBeGreaterThanOrEqual(2);
    for (const d of doms) expect(d).toEqual([0, 1]);
  });
});

test.describe('responsive chart geometry · desktop', () => {
  test('desktop: two fuel panels side by side', async ({ page }) => {
    await openLab(page, 'combustion', 'dark');
    await waitForPlot(page);
    const doms = await page.evaluate(() => {
      const gd = document.querySelector('.js-plotly-plot') as unknown as { _fullLayout: Record<string, { domain?: number[] }> };
      return Object.entries(gd._fullLayout).filter(([k]) => /^xaxis\d*$/.test(k)).map(([, v]) => v.domain![1]);
    });
    expect(Math.min(...doms)).toBeLessThan(0.6);
  });
});

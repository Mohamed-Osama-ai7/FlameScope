import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openLab, waitForPlot } from './helpers';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', '..', '..', 'docs', 'screenshots', 'lab');
mkdirSync(OUT, { recursive: true });

/** Disable text-cursor flicker and hide the live API pill (depends on whether the backend is running). */
async function stabilise(page: import('@playwright/test').Page) {
  await page.addStyleTag({ content: '.status-pill{visibility:hidden} *{caret-color:transparent!important}' });
  await page.waitForTimeout(300);
}

const shots: { name: string; hash: string; theme: 'dark' | 'light'; viewport?: { width: number; height: number }; plot?: boolean; full?: boolean; inspector?: boolean }[] = [
  { name: 'overview-desktop-dark', hash: 'overview', theme: 'dark', full: true },
  { name: 'overview-desktop-light', hash: 'overview', theme: 'light', full: true },
  { name: 'combustion-explorer-desktop-dark', hash: 'combustion', theme: 'dark', plot: true, full: true },
  { name: 'combustion-explorer-desktop-light', hash: 'combustion', theme: 'light', plot: true, full: true },
  { name: 'observations-table-desktop-dark', hash: 'observations', theme: 'dark' },
  { name: 'evidence-inspector-desktop-dark', hash: 'observations', theme: 'dark', inspector: true },
  { name: 'evidence-inspector-desktop-light', hash: 'observations', theme: 'light', inspector: true },
  { name: 'combustion-explorer-mobile-dark', hash: 'combustion', theme: 'dark', plot: true, viewport: { width: 390, height: 844 }, full: true },
  { name: 'overview-mobile-light', hash: 'overview', theme: 'light', viewport: { width: 390, height: 844 }, full: true },
];

for (const s of shots) {
  test(`screenshot + visual regression: ${s.name}`, async ({ page }, testInfo) => {
    if (s.viewport) await page.setViewportSize(s.viewport);
    await openLab(page, s.hash, s.theme);
    if (s.plot) await waitForPlot(page);
    if (s.inspector) {
      await page.getByRole('button', { name: /Inspect PSI69-r001/ }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
    }
    await stabilise(page);
    // Documentation screenshot of the actual running page.
    const suffix = testInfo.project.name === 'chromium' ? '' : `.${testInfo.project.name}`;
    await page.screenshot({ path: join(OUT, `${s.name}${suffix}.png`), fullPage: s.full ?? false });
    // Regression baseline (viewport-sized to stay stable).
    await expect(page).toHaveScreenshot(`${s.name}.png`, { fullPage: false, animations: 'disabled' });
  });
}

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { openLab } from './helpers';

test.describe('QUASAR entry', () => {
  test('is the default route and leads into the unchanged Lab', async ({ page }) => {
    await page.addInitScript(() => { try { localStorage.setItem('flamescope-theme', 'dark'); } catch { /* ignore */ } });
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'QUASAR' })).toBeVisible();
    await expect(page).toHaveTitle(/QUASAR/);
    await expect(page.getByText('Credit: NASA')).toBeVisible();
    await expect(page.getByText(/not affiliated with, endorsed by, or certified by NASA/)).toBeVisible();
    await page.getByRole('link', { name: 'Enter the Lab →' }).first().click();
    await expect(page.getByRole('navigation', { name: 'Lab sections' })).toBeVisible();
    await expect(page.getByRole('heading', { name: /What this dataset contains/ })).toBeVisible();
    await page.locator('a.brand').click();
    await expect(page.getByRole('heading', { level: 1, name: 'QUASAR' })).toBeVisible();
  });

  test('every Lab section keeps its hash route', async ({ page }) => {
    for (const hash of ['overview', 'explorer', 'comparison', 'analysis', 'vision', 'copilot', 'combustion', 'quality', 'observations']) {
      await openLab(page, hash);
      await expect(page.getByRole('navigation', { name: 'Lab sections' }).locator(`a[href="#${hash}"]`)).toHaveAttribute('aria-current', 'page');
    }
  });

  test('buoyancy slider scrubs the flame and is keyboard accessible', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    const slider = page.getByRole('slider', { name: /Gravity/ });
    await slider.scrollIntoViewIfNeeded();
    await expect(slider).toHaveValue('0'); // reduced motion: no autoplay, ends in microgravity
    await expect(page.locator('.q-flame-svg desc')).toContainText(/diffusion/);
    await slider.focus();
    await page.keyboard.press('End');
    await expect(slider).toHaveAttribute('aria-valuetext', /1\.00 g, Buoyant convection/);
    await expect(page.locator('.q-flame-svg desc')).toContainText(/rises/);
  });

  test('autoplay runs once from 1 g to 0 g without reduced motion', async ({ page }) => {
    await page.goto('/');
    const slider = page.getByRole('slider', { name: /Gravity/ });
    await slider.scrollIntoViewIfNeeded();
    await expect(slider).toHaveValue('0', { timeout: 8000 });
  });

  test('trust ledger shows live source states, or says they are unavailable (never invented)', async ({ page }) => {
    await page.route('**/api/v1/rag/sources', (route) => route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify([{ source_id: 'PSI-69', eligibility: 'PENDING_VERIFICATION', usable_as_evidence: true, registry_status: 'ACQUIRED', decision_owner: 'x', decided_on: '2026-11-13' }]) }));
    await page.goto('/');
    await expect(page.getByRole('list', { name: /Source eligibility/ })).toContainText('Pending verification');
    await page.unroute('**/api/v1/rag/sources');
    await page.route('**/api/v1/rag/sources', (route) => route.abort());
    await page.reload();
    await expect(page.getByText(/Live source states unavailable/)).toBeVisible();
  });

  test('filter rail only where filters apply', async ({ page }) => {
    await openLab(page, 'copilot');
    await expect(page.locator('.filters-wrap')).toBeHidden();
    await openLab(page, 'vision');
    await expect(page.locator('.filters-wrap')).toBeHidden();
    await openLab(page, 'combustion');
    await expect(page.locator('.filters-wrap')).toBeVisible();
  });

  test('landing has no serious accessibility violations', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('heading', { level: 1, name: 'QUASAR' }).waitFor();
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')).toEqual([]);
  });
});

import { expect, test } from '@playwright/test';
import { openLab } from './helpers';

test.describe('Physics Analysis Engine E2E', () => {
  test('navigates to Physics Analysis and renders subnav tabs and offline baseline', async ({ page }) => {
    await openLab(page, 'analysis');

    // Section heading
    await expect(page.getByRole('heading', { name: 'Analysis Results', level: 2 })).toBeVisible();

    // Verification badges
    await expect(page.locator('.status-badges .status-pill')).toContainText(/Verified Baseline|Live API/i);
    await expect(page.getByText('FLEX Droplet')).toBeVisible();

    // Subnav tabs exist
    const subnav = page.locator('nav.subnav');
    await expect(subnav.getByRole('button', { name: /d²-Law Consistency/i })).toBeVisible();
    await expect(subnav.getByRole('button', { name: /Oxygen Index Effect/i })).toBeVisible();
    await expect(subnav.getByRole('button', { name: /Published Analysis Strata/i })).toBeVisible();
  });

  test('d2-consistency tab displays fuel summaries and filters runs table', async ({ page }) => {
    await openLab(page, 'analysis');

    // d2 consistency view should be active by default
    await expect(page.getByRole('heading', { name: /Consistency of Reported FLEX Burning Times/i })).toBeVisible();

    // Summary cards exist for fuels
    await expect(page.getByRole('heading', { name: 'Heptane' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Methanol' })).toBeVisible();

    // Filter controls row exists
    const fuelSelect = page.locator('.filter-controls-row select').first();
    await expect(fuelSelect).toBeVisible();

    // Filter by Heptane
    await fuelSelect.selectOption('Heptane');
    await expect(page.getByRole('heading', { name: 'Heptane' })).toBeVisible();

    // Search input
    const searchInput = page.getByPlaceholder(/Search run ID/i);
    await searchInput.fill('PSI-69-r002');

    // Clear search and switch back to all
    await searchInput.fill('');
    await fuelSelect.selectOption('all');

    // Flagged runs section
    await expect(page.getByRole('heading', { name: /Flagged for Review/i })).toBeVisible();
  });

  test('oxygen effect tab displays multivariable regression models and abstentions', async ({ page }) => {
    await openLab(page, 'analysis');

    // Switch to Oxygen Index Effect tab
    await page.locator('nav.subnav').getByRole('button', { name: /Oxygen Index Effect/i }).click();

    // Heading for oxygen effect
    await expect(page.getByRole('heading', { name: /Multivariable OLS/i })).toBeVisible();

    // Stratum cards
    const stratumCards = page.locator('.physics-card');
    await expect(stratumCards.first()).toBeVisible();

    // Scientific limitations callout
    await expect(page.getByText(/Methodology & Limitations/i)).toBeVisible();
  });

  test('published strata tab renders baseline strata tables', async ({ page }) => {
    await openLab(page, 'analysis');

    // Switch to Published Analysis Strata tab
    await page.locator('nav.subnav').getByRole('button', { name: /Published Analysis Strata/i }).click();

    // Baseline strata cards exist
    await expect(page.locator('.physics-card').first()).toBeVisible();
  });
});

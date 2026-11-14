import { expect, test } from '@playwright/test';
import { openLab } from './helpers';

test.describe('Physics Analysis Engine E2E', () => {
  test('navigates to Physics Analysis and renders subnav tabs and offline baseline', async ({ page }) => {
    await openLab(page, 'analysis');

    // Section heading
    await expect(page.getByRole('heading', { name: /Combustion Physics & Published Results/i })).toBeVisible();

    // Verification badges
    await expect(page.locator('.status-badges')).toContainText(/Verified Baseline|Live API/i);
    await expect(page.getByText(/PSI-69 FLEX Evidence/i)).toBeVisible();

    // Subnav tabs exist
    const subnav = page.locator('.subnav');
    await expect(subnav.getByRole('tab', { name: /d²-Law Consistency/i })).toBeVisible();
    await expect(subnav.getByRole('tab', { name: /Oxygen Effect on K/i })).toBeVisible();
    await expect(subnav.getByRole('tab', { name: /Published Correlation Strata/i })).toBeVisible();
  });

  test('d2-consistency tab displays fuel summaries and filters runs table', async ({ page }) => {
    await openLab(page, 'analysis');

    // d2 consistency view is active by default
    await expect(page.getByText(/Physics Diagnostic Contract/i)).toBeVisible();

    // Summary cards exist for fuels
    await expect(page.getByText('Heptane Fuel')).toBeVisible();
    await expect(page.getByText('Methanol Fuel')).toBeVisible();

    // Filter controls row exists
    const fuelSelect = page.getByLabel(/Filter fuel for d2 consistency/i);
    await expect(fuelSelect).toBeVisible();

    // Filter by Heptane
    await fuelSelect.selectOption('Heptane');
    await expect(page.getByText('Heptane Fuel')).toBeVisible();

    // Expand full table to reveal search
    await page.getByRole('button', { name: /Expand Full Table/i }).click();

    // Search input
    const searchInput = page.getByPlaceholder(/Search run ID/i);
    await searchInput.fill('PSI-69-r002');

    // Clear search and switch back to all
    await searchInput.fill('');
    await fuelSelect.selectOption('all');

    // Flagged runs section
    await expect(page.getByRole('heading', { name: /Flagged.*Review/i })).toBeVisible();
  });

  test('oxygen effect tab displays multivariable regression models and abstentions', async ({ page }) => {
    await openLab(page, 'analysis');

    // Switch to Oxygen Effect tab
    await page.locator('.subnav').getByRole('tab', { name: /Oxygen Effect on K/i }).click();

    // Contract callout and heading
    await expect(page.getByText(/Within-Stratum OLS Regression Contract/i)).toBeVisible();
    await expect(page.getByRole('heading', { name: /Computable Experimental Strata/i })).toBeVisible();

    // Stratum cards
    const stratumCards = page.locator('.physics-card');
    await expect(stratumCards.first()).toBeVisible();

    // Abstained strata section
    await expect(page.getByRole('heading', { name: /Abstained Strata/i })).toBeVisible();
  });

  test('published strata tab renders baseline strata tables', async ({ page }) => {
    await openLab(page, 'analysis');

    // Switch to Published Correlation Strata tab
    await page.locator('.subnav').getByRole('tab', { name: /Published Correlation Strata/i }).click();

    // Baseline strata cards exist
    await expect(page.locator('.analysis-result-group').first()).toBeVisible();
  });
});

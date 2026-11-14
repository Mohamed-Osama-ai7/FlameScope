import { expect, test } from '@playwright/test';
import { openLab } from './helpers';

test.describe('Flame Vision Metrology E2E', () => {
  test('navigates to Flame Vision and displays scientific safeguards and evaluation table', async ({ page }) => {
    await openLab(page, 'vision');

    // Section heading
    await expect(page.getByRole('heading', { name: 'Flame Vision & Metrology', level: 2 })).toBeVisible();

    // Critical Scientific Safeguards Banner
    const safeguards = page.locator('.callout.warning').first();
    await expect(safeguards).toBeVisible();
    await expect(safeguards).toContainText('Scale-Free Metrology Only');
    await expect(safeguards).toContainText('Systematic 15–22% Gap vs NASA Reported Rate (Unresolved Hypotheses)');
    await expect(safeguards).toContainText('Goodness-of-Fit ≠ Physical Accuracy');
    await expect(safeguards).toContainText('Scientific Abstention on Sooting Fuels');

    // Overview tab active by default
    await expect(page.getByRole('heading', { name: /Evaluation Benchmark/i })).toBeVisible();

    // Inferred uncalibrated scale label
    await expect(page.getByText(/Inferred Scale Range \(Uncalibrated\):/i)).toBeVisible();

    // Evaluation table lists tests
    const evalTable = page.locator('.data-table');
    await expect(evalTable).toBeVisible();
    await expect(evalTable.getByText('20CAL10')).toBeVisible();
    await expect(evalTable.getByText('20CAL12')).toBeVisible();
    await expect(evalTable.getByText('30CAL06')).toBeVisible();

    // 30CAL06 has Abstained badge
    const abstainedRow = evalTable.locator('tr', { hasText: '30CAL06' });
    await expect(abstainedRow.locator('.badge.warning')).toHaveText('Abstained');
  });

  test('abstained test 30CAL06 displays root-cause panel without fake burning rate', async ({ page }) => {
    await openLab(page, 'vision');

    // Switch to Test Inspector
    await page.locator('nav.subnav').getByRole('button', { name: /Test Inspector/i }).click();

    // Select 30CAL06
    const select = page.locator('.filter-controls-row select').first();
    await select.selectOption('30CAL06');

    // Abstention panel
    const panel = page.locator('.abstained-panel');
    await expect(panel).toBeVisible();
    await expect(panel.getByRole('heading', { name: /Measurement Abstained: 30CAL06/i })).toBeVisible();
    await expect(panel).toContainText('too few measured frames after the igniters left the field of view');
    await expect(panel).toContainText('sooting heptane droplets generate an expanding soot shell');

    // No scale-free burning rate metric displayed for abstained test
    await expect(panel.getByRole('heading', { name: /Scale-Free Burning Rate/i })).not.toBeVisible();
  });

  test('computable test 20CAL10 displays metrology metrics, sensitivity, and provenance', async ({ page }) => {
    await openLab(page, 'vision');

    // Switch to Test Inspector
    await page.locator('nav.subnav').getByRole('button', { name: /Test Inspector/i }).click();

    // Select 20CAL10
    const select = page.locator('.filter-controls-row select').first();
    await select.selectOption('20CAL10');

    // Scale-Free Burning Rate
    await expect(page.getByRole('heading', { name: /Scale-Free Burning Rate/i })).toBeVisible();
    await expect(page.getByText('0.1348').first()).toBeVisible();

    // Linear fit card
    await expect(page.getByRole('heading', { name: /Linear Fit/i })).toBeVisible();

    // Threshold sensitivity table
    await expect(page.getByRole('heading', { name: /Threshold Sensitivity/i })).toBeVisible();
    await expect(page.getByText('f = 0.5 (nominal half-intensity)')).toBeVisible();

    // Visual Evidence & Provenance
    await expect(page.getByRole('heading', { name: /Original Droplet Segmentation Overlay/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Cryptographic Source File Manifest/i })).toBeVisible();
  });

  test('time-series tab renders dynamic SVG chart and frame records', async ({ page }) => {
    await openLab(page, 'vision');

    // Switch to Time-Series & Dynamics tab
    await page.locator('nav.subnav').getByRole('button', { name: /Time-Series & Dynamics/i }).click();

    // Chart heading
    await expect(page.getByRole('heading', { name: /D²\(t\) Evolution & OLS Fit/i })).toBeVisible();

    // SVG chart element exists
    const chartSvg = page.locator('svg').filter({ has: page.locator('line') });
    await expect(chartSvg.first()).toBeVisible();

    // Frame records table
    await expect(page.getByRole('heading', { name: /Frame Records/i })).toBeVisible();

    // Filter frames by status
    const filterSelect = page.locator('.filter-controls-row select').nth(2);
    await filterSelect.selectOption('measured');
    await expect(page.locator('.compact-table tbody tr').first()).toBeVisible();
  });

  test('method card tab renders formulas, assumptions and limits', async ({ page }) => {
    await openLab(page, 'vision');

    // Switch to Method Card tab
    await page.locator('nav.subnav').getByRole('button', { name: /Method Card & Validity/i }).click();

    // Method specification heading & eyebrow
    await expect(page.getByText('METHOD SPECIFICATION')).toBeVisible();
    await expect(page.getByRole('heading', { name: /Backlit droplet diameter/i })).toBeVisible();
    await expect(page.getByText('vision.hibms_droplet_d2_pixel')).toBeVisible();
    await expect(page.getByRole('heading', { name: /Assumptions/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Validity Limits & Failure Modes/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Quality Gates & Abstention Conditions/i })).toBeVisible();
  });
});

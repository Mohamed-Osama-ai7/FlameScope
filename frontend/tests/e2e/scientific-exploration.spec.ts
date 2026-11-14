import { expect, test } from '@playwright/test';
import { openLab } from './helpers';

const comparable = {
  classification: 'direct',
  shared_axis_allowed: true,
  reasons: [],
  held_constant: ['regime', 'variable', 'unit'],
  differing: [],
  unknown: ['apparatus'],
};

test.describe('scientific explorer API workflow', () => {
  test('loads registry records and opens a searched experiment with source provenance', async ({ page }) => {
    await page.route('**/api/v1/sources', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        source_id: 'PSI-69',
        source_title: 'FLEX droplet combustion dataset',
        source_type: 'dataset',
        official_challenge_resource: false,
        source_url: 'https://example.test/flex.csv',
        doi: '10.60555/mbq8-0451',
        version_or_release: 'v1',
        retrieved_at_utc: '2026-11-13T00:00:00Z',
        license: 'CC0-1.0',
        raw_file_path: 'data/raw/flex.csv',
        sha256: 'a'.repeat(64),
        verification_status: 'VERIFIED',
        notes: 'Source metadata from the API.',
      }]),
    }));
    await page.route('**/api/v1/regimes', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ regime: 'flex_droplet', description: 'Droplet combustion in FLEX.', variables: ['oxygen', 'pressure'] }]),
    }));
    await page.route('**/api/v1/methods', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        method_id: 'd2-law-fit', version: '1.0', title: 'Droplet d²-law fit', regimes: ['flex_droplet'],
        formula: 'D²(t) = D₀² − Kt', variables: [{ symbol: 'K', name: 'burning-rate constant', unit: 'mm²/s', role: 'output' }],
        references: [{ citation: 'Combustion reference', doi: null }], assumptions: ['Spherical droplet'],
        validity_limits: ['FLEX droplet regime'], required_inputs: ['diameter series'], uncertainty_method: 'Weighted fit',
        validation: ['Not validated on this source'], abstention_conditions: ['Insufficient points'], status: 'planned',
      }]),
    }));

    await openLab(page, 'explorer');
    await expect(page.getByText('FLEX droplet combustion dataset')).toBeVisible();
    await expect(page.getByText('Droplet combustion in FLEX.')).toBeVisible();
    await expect(page.getByText('Droplet d²-law fit')).toBeVisible();
    await page.getByLabel('Find an experiment').fill('PSI69-r001');
    await expect(page.locator('.explorer-record-table tbody tr')).toHaveCount(1);
    await page.getByRole('button', { name: 'FLEX-001', exact: true }).click();
    const inspector = page.getByRole('dialog', { name: /FLEX-/ });
    await expect(inspector).toBeVisible();
    await expect(inspector.getByRole('link', { name: /DOI 10.60555\/mbq8-0451/ })).toBeVisible();
  });

  test('shows registry API errors and retries into an explicit empty state', async ({ page }) => {
    let sourceRequestCount = 0;
    await page.route('**/api/v1/sources', async (route) => {
      sourceRequestCount += 1;
      if (sourceRequestCount === 1) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Registry temporarily unavailable.' }) });
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      }
    });
    await page.route('**/api/v1/regimes', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
    await page.route('**/api/v1/methods', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));

    await openLab(page, 'explorer');
    await expect(page.getByRole('alert')).toContainText('Registry temporarily unavailable.');
    await page.getByRole('button', { name: 'Retry all registry requests' }).click();
    await expect(page.getByText('No sources are registered in the API yet.')).toBeVisible();
    await expect(page.getByText('No combustion regimes are available.')).toBeVisible();
    await expect(page.getByText('No analysis methods are registered.')).toBeVisible();
    expect(sourceRequestCount).toBe(2);
  });

  test('displays live scientific database status and runs when data platform is connected', async ({ page }) => {
    await page.route('**/api/v1/sources', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    }));
    await page.route('**/api/v1/regimes', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
    await page.route('**/api/v1/methods', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
    await page.route('**/api/v1/data-platform/status', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        database_configured: true,
        database_reachable: true,
        schema_revision: '0001',
        expected_schema_revision: '0001',
        investigations_loaded: ['PSI-69'],
        official_challenge_resource_loaded: true,
        runs: 274,
        measurements: 2466,
        detail: null,
      }),
    }));

    await openLab(page, 'explorer');
    await expect(page.getByText('Scientific Data Platform Database')).toBeVisible();
    await expect(page.getByText('Database Connected')).toBeVisible();
    await expect(page.getByText('274 runs')).toBeVisible();
    await expect(page.getByText('2466 cells')).toBeVisible();
  });
});

test.describe('comparison validation guardrail', () => {
  test('shows the engine explanation and withholds a shared chart when comparison is rejected', async ({ page }) => {
    let postedBody: { a: Record<string, unknown>; b: Record<string, unknown> } | undefined;
    await page.route('**/api/v1/comparisons/validate', async (route) => {
      postedBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...comparable,
          classification: 'not_comparable',
          shared_axis_allowed: false,
          reasons: ['The selected runs have different recorded oxygen conditions.'],
          differing: ['ambient_oxygen_mole_fraction'],
        }),
      });
    });

    await openLab(page, 'comparison');
    await expect(page.getByRole('heading', { name: 'not comparable' })).toBeVisible();
    await expect(page.getByText('The selected runs have different recorded oxygen conditions.')).toBeVisible();
    await expect(page.getByText('Keep runs off a shared quantitative axis')).toBeVisible();
    await expect(page.locator('.comparison-plot')).toHaveCount(0);
    expect(postedBody?.a).toMatchObject({ investigation_id: 'PSI-69', regime: 'flex_droplet', unit: 'mm^2/s' });
    expect(postedBody?.b).toMatchObject({ investigation_id: 'PSI-69', regime: 'flex_droplet', unit: 'mm^2/s' });
  });

  test('renders the shared comparison and evidence table only after the API allows it', async ({ page }) => {
    await page.route('**/api/v1/comparisons/validate', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(comparable),
    }));

    await openLab(page, 'comparison');
    await expect(page.getByText('Shared quantitative axis allowed')).toBeVisible();
    await expect(page.locator('.comparison-plot')).toBeVisible();
    await page.getByText('Validated comparison values as a table').click();
    await expect(page.getByRole('button', { name: 'Inspect evidence' })).toHaveCount(2);
    await page.getByRole('button', { name: 'Inspect evidence' }).first().click();
    await expect(page.getByRole('dialog', { name: /FLEX-/ })).toBeVisible();
    await expect(page.getByRole('dialog')).toContainText('Provenance');
  });
});

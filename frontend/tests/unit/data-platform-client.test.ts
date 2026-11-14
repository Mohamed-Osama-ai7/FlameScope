import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../src/api/client';
import type {
  ArtifactRecord,
  DataPlatformStatus,
  MeasurementRecord,
  PaginatedResult,
  ProvenanceRecord,
  RunDetail,
  RunSummary,
} from '../../src/api/contracts';

afterEach(() => vi.unstubAllGlobals());

const sampleRun: RunSummary = {
  run_id: 'PSI-69-r001',
  investigation_id: 'PSI-69',
  source_row: 1,
  source_identifier: '20CAL08',
  source_record_key: 'PSI69-r001|FLEX-001|20CAL08|3/5/2009|17:22:03',
  combustion_regime: 'flex_droplet',
  material_or_fuel: 'Heptane',
  test_date: '2009-03-05',
  test_date_raw: '3/5/2009',
  test_time_gmt_raw: '17:22:03',
  end_mode: 'Disruption',
  quality_flags: [],
  derived_attributes: { fuel: 'Heptane' },
  source_locator: 'PSI-69_Experimental table_FLEX.csv#csv_line=2&flex_test=1',
};

const sampleArtifact: ArtifactRecord = {
  artifact_id: '11111111-1111-1111-1111-111111111111',
  investigation_id: 'PSI-69',
  artifact_kind: 'dataset_table',
  file_name: 'PSI-69_Experimental table_FLEX.csv',
  relative_path: 'data/raw/PSI-69/experimental_table/PSI-69_Experimental table_FLEX.csv',
  media_type: 'text/csv',
  text_encoding: 'utf-8',
  byte_size: 1048576,
  sha256: 'a'.repeat(64),
  source_url: 'https://psi.nasa.gov/flex.csv',
  source_version: '1.0',
  license_id: 'CC0-1.0',
  retrieved_at: '2026-11-13T00:00:00Z',
};

const sampleMeasurement: MeasurementRecord = {
  measurement_id: '22222222-2222-2222-2222-222222222222',
  run_id: 'PSI-69-r001',
  variable_name: 'initial_droplet_diameter',
  role: 'initial_condition',
  value: 4.67,
  value_status: 'parsed',
  original_value_text: '4.67',
  unit: 'mm',
  measured_or_derived: 'measured',
  usable_for_analysis: true,
  quality_flags: [],
  attributes: {},
  uncertainty_value: null,
  uncertainty_type: null,
  coverage_factor: null,
  source_column: 'Initial Droplet Diameter (mm)',
  source_locator: 'PSI-69_Experimental table_FLEX.csv#csv_line=2&col=4',
};

function mockJsonResponse(payload: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    text: () => Promise.resolve(JSON.stringify(payload)),
  }));
}

describe('Data Platform API client', () => {
  it('parses platform status when database is reachable', async () => {
    const statusPayload: DataPlatformStatus = {
      database_configured: true,
      database_reachable: true,
      schema_revision: '0001',
      expected_schema_revision: '0001',
      investigations_loaded: ['PSI-69'],
      official_challenge_resource_loaded: true,
      runs: 274,
      measurements: 2466,
      detail: null,
    };
    mockJsonResponse(statusPayload);
    const result = await api.getDataPlatformStatus();
    expect(result.database_reachable).toBe(true);
    expect(result.runs).toBe(274);
    expect(result.investigations_loaded).toContain('PSI-69');
  });

  it('preserves 503 error when database is not configured', async () => {
    mockJsonResponse({ detail: 'Scientific database not configured (FLAMESCOPE_DATABASE_URL is not set).' }, 503);
    await expect(api.getDataPlatformStatus()).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      message: 'Scientific database not configured (FLAMESCOPE_DATABASE_URL is not set).',
    });
  });

  it('lists paginated runs and preserves source_record_key', async () => {
    const listPayload: PaginatedResult<RunSummary> = {
      items: [sampleRun],
      total: 1,
      limit: 10,
      offset: 0,
    };
    mockJsonResponse(listPayload);
    const result = await api.listRuns({ fuel: 'Heptane', limit: 10 });
    expect(result.total).toBe(1);
    expect(result.items[0].run_id).toBe('PSI-69-r001');
    expect(result.items[0].source_record_key).toBe('PSI69-r001|FLEX-001|20CAL08|3/5/2009|17:22:03');
  });

  it('retrieves detailed run with artifact and 9 measurements', async () => {
    const detailPayload: RunDetail = {
      ...sampleRun,
      artifact: sampleArtifact,
      measurements: [sampleMeasurement],
    };
    mockJsonResponse(detailPayload);
    const result = await api.getRun('PSI-69-r001');
    expect(result.run_id).toBe('PSI-69-r001');
    expect(result.artifact.file_name).toBe('PSI-69_Experimental table_FLEX.csv');
    expect(result.measurements).toHaveLength(1);
    expect(result.measurements[0].value).toBe(4.67);
  });

  it('retrieves full measurement provenance tracing back to original NASA file', async () => {
    const provPayload: ProvenanceRecord = {
      measurement: sampleMeasurement,
      source_cell: {
        file_name: 'PSI-69_Experimental table_FLEX.csv',
        source_row: 1,
        source_column: 'Initial Droplet Diameter (mm)',
        original_value_text: '4.67',
        original_unit_label: 'mm',
        platform_unit: 'mm',
        unit_evidence: null,
        source_locator: 'PSI-69_Experimental table_FLEX.csv#csv_line=2&col=4',
      },
      run: sampleRun,
      investigation: {
        investigation_id: 'PSI-69',
        title: 'FLEX droplet combustion',
        acronym: 'FLEX',
        combustion_regime: 'flex_droplet',
        source_repository: 'PSI Data Repository',
        source_url: 'https://psi.nasa.gov',
        doi: '10.60555/mbq8-0451',
        license_id: 'CC0-1.0',
        research_area: 'Combustion Science',
        official_challenge_resource: false,
        registry_status: 'ACQUIRED',
      },
      artifact: sampleArtifact,
      extraction: {
        extraction_run_id: '33333333-3333-3333-3333-333333333333',
        extractor_name: 'psi69_flex_experimental_table',
        extractor_version: '1.0.0',
        inputs_json: {},
        parameters_json: {},
        code_revision: 'abc',
        run_count: 274,
        measurement_count: 2466,
        first_loaded_at: '2026-11-13T00:00:00Z',
        last_loaded_at: '2026-11-13T00:00:00Z',
      },
      extraction_method: 'Structured CSV cell extraction with header-based variable mapping',
      how_to_verify: 'Inspect raw CSV at source_locator',
    };
    mockJsonResponse(provPayload);
    const result = await api.getMeasurementProvenance('22222222-2222-2222-2222-222222222222');
    expect(result.source_cell.file_name).toBe('PSI-69_Experimental table_FLEX.csv');
    expect(result.source_cell.original_value_text).toBe('4.67');
    expect(result.investigation.investigation_id).toBe('PSI-69');
  });

  it('rejects malformed run responses', async () => {
    mockJsonResponse({ items: [{ run_id: 123 }] }); // bad type
    await expect(api.listRuns()).rejects.toThrow();
  });
});

/**
 * SYNTHETIC stress tests. Records here are generated, flagged synthetic: true, and must never reach
 * scientific outputs: the loader and every export refuse them unless explicitly allowed in tests.
 */
import { describe, expect, it } from 'vitest';
import { analysisSummary, ExportError, recordsToCsv } from '../../src/lab/data/export';
import { DatasetError, validateDataset } from '../../src/lab/data/load';
import { defaultFilters, viewData, VIEWS } from '../../src/lab/data/selectors';
import { scatterFigure, SERIES } from '../../src/lab/charts/specs';
import type { FlexRecord, LabDataset } from '../../src/lab/data/types';

function syntheticDataset(n: number): LabDataset {
  const modes = ['free_floating', 'fiber_translated', 'fiber_translation_not_stated'] as const;
  const records: FlexRecord[] = Array.from({ length: n }, (_, i) => {
    const o2 = 0.12 + (i % 23) * 0.01;
    const values = {
      ambient_pressure: i % 2 ? 760 : 532, ambient_oxygen_mole_fraction: o2, ambient_nitrogen_mole_fraction: 1 - o2,
      co2_mole_fraction: 0, ambient_helium_mole_fraction: 0, initial_droplet_diameter: 2 + (i % 17) / 10,
      extinction_diameter: i % 5 ? 1 + (i % 7) / 10 : null, burning_rate_constant_mm2_s: i % 11 ? 0.3 + (i % 13) / 40 : null, burn_time_s: 5,
    };
    const usable = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v !== null])) as FlexRecord['usable'];
    return {
      record_key: `SYNTH-${i}`, psi_row: i + 1, flex_test_number: i + 1, identifier: `SYN${i}`, test_date: '1/1/2000', test_gmt: null,
      fuel: i % 2 ? 'Methanol' : 'Heptane', test_end: 'Extinction', values, raw: Object.fromEntries(Object.keys(values).map((k) => [k, ''])) as FlexRecord['raw'],
      field_flags: {}, row_flags: [], usable, diluent_family: 'N2_only', pressure_cluster: i % 2 ? '~1 atm nominal (synthetic)' : '~0.7 atm nominal (synthetic)',
      composition_sum: 1, support_mode: modes[i % 3], support_basis: 'synthetic', dext_origin: 'reported_extinction_no_extrapolation_noted',
      sensitivity_tags: [], eligible: values.burning_rate_constant_mm2_s === null ? [] : ['A1', 'A5'],
      evidence: { table_ix_pdf_page: 0, table_ix_printed_page: 0, caption_figure: null, caption_pdf_page: null, caption: null, matrix_table: null,
        matrix_table_fiber: null, matrix_table_pressure_atm: null, pressure_source_conflict: null, shutter_1_30s_period: false, coated_needle_period: false,
        documented_contamination_or_feature: null, dext_caption_note: null, match_method: 'synthetic', verification_status: 'synthetic' },
    };
  });
  return {
    dataset: 'SYNTHETIC', dataset_version: 'synthetic', analysis_version: 'synthetic', synthetic: true, value_origin: 'SYNTHETIC — not NASA data',
    provenance: {} as LabDataset['provenance'],
    scope: { records: n, unique_flex_tests: n, unique_identifiers: n, nasa_stated_tests: 0, table_ix_printed_rows: 0, table_ix_rows_not_in_psi: [] },
    units: {} as LabDataset['units'], raw_headers: {} as LabDataset['raw_headers'], rules: {}, unknown_fields: [],
    outcome_caveats: { Methanol: '', Heptane: '' }, records, strata: [],
  };
}

const theme = { mode: 'light' as const, bg: '#fff', fg: '#000', muted: '#555', grid: '#eee', axis: '#999', series: SERIES.light, font: 'Inter' };

describe('synthetic data guard', () => {
  it('the lab loader rejects synthetic datasets', () => {
    expect(() => validateDataset(syntheticDataset(10))).toThrow(DatasetError);
  });
  it('every export refuses synthetic data unless explicitly allowed in tests', () => {
    const s = syntheticDataset(10);
    expect(() => recordsToCsv(s, s.records)).toThrow(ExportError);
    expect(() => analysisSummary(s, defaultFilters(s.records))).toThrow(ExportError);
  });
});

describe('synthetic stress benchmarks (timings printed; generous ceilings only catch regressions)', () => {
  for (const n of [274, 5_000, 50_000]) {
    it(`filter + view + figure + CSV for ${n} synthetic records`, () => {
      const s = validateDataset(syntheticDataset(n), { allowSynthetic: true });
      s.units = { burning_rate_constant_mm2_s: 'mm²/s', ambient_oxygen_mole_fraction: 'mole fraction' } as LabDataset['units'];
      const f = { ...defaultFilters(s.records), supportModes: ['free_floating', 'fiber_translated', 'fiber_translation_not_stated'] as never };
      const t0 = performance.now();
      const vd = viewData(s.records, VIEWS.k_o2, f);
      const t1 = performance.now();
      const fig = scatterFigure(s, vd, theme, null);
      const t2 = performance.now();
      const csv = recordsToCsv(s, s.records, { allowSynthetic: true });
      const t3 = performance.now();
      const pts = fig.data.reduce((a, tr) => a + ((tr as { x?: unknown[] }).x?.length ?? 0), 0);
      expect(pts).toBe(vd.shown.length);
      expect(csv.split('\n').length - 2).toBe(n);
      console.log(`[bench] n=${n} viewData=${(t1 - t0).toFixed(1)}ms figure=${(t2 - t1).toFixed(1)}ms csv=${(t3 - t2).toFixed(1)}ms points=${pts}`);
      expect(t3 - t0).toBeLessThan(n <= 5_000 ? 2_000 : 20_000);
    });
  }
});

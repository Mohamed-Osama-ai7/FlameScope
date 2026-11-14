/**
 * SYNTHETIC records for rendering benchmarks only. Deterministic (seeded), flagged synthetic: true,
 * and kept out of src/: the application and every scientific output can never import this file.
 */
import type { FlexRecord, LabDataset, NumericField } from '../src/lab/data/types';
import { NUMERIC_FIELDS } from '../src/lab/data/types';

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function syntheticRecords(n: number, seed = 20261113): FlexRecord[] {
  const rnd = mulberry32(seed);
  return Array.from({ length: n }, (_, i) => {
    const o2 = 0.12 + rnd() * 0.22;
    const values = {
      ambient_pressure: i % 2 ? 760 : 532,
      ambient_oxygen_mole_fraction: o2,
      ambient_nitrogen_mole_fraction: 1 - o2,
      co2_mole_fraction: 0,
      ambient_helium_mole_fraction: 0,
      initial_droplet_diameter: 1.5 + rnd() * 3,
      extinction_diameter: 0.5 + rnd() * 3,
      burning_rate_constant_mm2_s: 0.2 + o2 * 1.2 + (rnd() - 0.5) * 0.15,
      burn_time_s: 5,
    } as Record<NumericField, number | null>;
    const usable = Object.fromEntries(NUMERIC_FIELDS.map((f) => [f, true])) as FlexRecord['usable'];
    const raw = Object.fromEntries(NUMERIC_FIELDS.map((f) => [f, ''])) as FlexRecord['raw'];
    return {
      record_key: `SYNTH-${i}`, psi_row: i + 1, flex_test_number: i + 1, identifier: `SYN${i}`,
      test_date: '1/1/2000', test_gmt: null, fuel: i % 3 === 0 ? 'Heptane' : 'Methanol', test_end: 'Extinction',
      values, raw, field_flags: {}, row_flags: [], usable, diluent_family: 'N2_only',
      pressure_cluster: i % 2 ? '~1 atm nominal (synthetic)' : '~0.7 atm nominal (synthetic)', composition_sum: 1,
      support_mode: 'free_floating', support_basis: 'synthetic', dext_origin: 'reported_extinction_no_extrapolation_noted',
      sensitivity_tags: [], eligible: ['A1'],
      evidence: { table_ix_pdf_page: 0, table_ix_printed_page: 0, caption_figure: null, caption_pdf_page: null, caption: null,
        matrix_table: null, matrix_table_fiber: null, matrix_table_pressure_atm: null, pressure_source_conflict: null,
        shutter_1_30s_period: false, coated_needle_period: false, documented_contamination_or_feature: null,
        dext_caption_note: null, match_method: 'synthetic', verification_status: 'synthetic' },
    };
  });
}

export function syntheticDataset(records: FlexRecord[]): LabDataset {
  return {
    dataset: 'SYNTHETIC', dataset_version: 'synthetic', analysis_version: 'synthetic', synthetic: true,
    value_origin: 'SYNTHETIC - not NASA data', provenance: {} as LabDataset['provenance'],
    scope: { records: records.length, unique_flex_tests: records.length, unique_identifiers: records.length, nasa_stated_tests: 0,
      table_ix_printed_rows: 0, table_ix_rows_not_in_psi: [] },
    units: { ambient_pressure: 'mmHg', ambient_oxygen_mole_fraction: 'mole fraction', ambient_nitrogen_mole_fraction: 'mole fraction',
      co2_mole_fraction: 'mole fraction', ambient_helium_mole_fraction: 'mole fraction', initial_droplet_diameter: 'mm',
      extinction_diameter: 'mm', burning_rate_constant_mm2_s: 'mm²/s', burn_time_s: 's' },
    raw_headers: {} as LabDataset['raw_headers'], rules: {}, unknown_fields: [], outcome_caveats: { Methanol: '', Heptane: '' },
    records, strata: [],
  };
}

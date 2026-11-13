/** Typed contract for frontend/public/data/flex_lab_dataset_v0.2.0.json (backend/scripts/export_lab_dataset.py). */

export type Fuel = 'Methanol' | 'Heptane';
export type SupportMode =
  | 'free_floating'
  | 'fiber_translated'
  | 'fiber_translation_not_stated'
  | 'conflicting_sources'
  | 'unknown';
export type DiluentFamily = 'N2_only' | 'CO2_added' | 'He_added' | 'CO2_and_He' | 'unknown';
export type AnalysisId = 'A1' | 'A2' | 'A3' | 'A4' | 'A5' | 'A6';

export const NUMERIC_FIELDS = [
  'ambient_pressure',
  'ambient_oxygen_mole_fraction',
  'ambient_nitrogen_mole_fraction',
  'co2_mole_fraction',
  'ambient_helium_mole_fraction',
  'initial_droplet_diameter',
  'extinction_diameter',
  'burning_rate_constant_mm2_s',
  'burn_time_s',
] as const;
export type NumericField = (typeof NUMERIC_FIELDS)[number];

export interface RecordEvidence {
  table_ix_pdf_page: number;
  table_ix_printed_page: number;
  caption_figure: number | null;
  caption_pdf_page: number | null;
  caption: string | null;
  matrix_table: string | null;
  matrix_table_fiber: string | null;
  matrix_table_pressure_atm: number | null;
  pressure_source_conflict: string | null;
  shutter_1_30s_period: boolean;
  coated_needle_period: boolean;
  documented_contamination_or_feature: string | null;
  dext_caption_note: string | null;
  match_method: string;
  verification_status: string;
}

export interface FlexRecord {
  record_key: string;
  psi_row: number;
  flex_test_number: number;
  identifier: string;
  test_date: string;
  test_gmt: string | null;
  fuel: Fuel;
  test_end: string;
  values: Record<NumericField, number | null>;
  raw: Record<NumericField, string>;
  field_flags: Partial<Record<NumericField, string[]>>;
  row_flags: string[];
  usable: Record<NumericField, boolean>;
  diluent_family: DiluentFamily;
  pressure_cluster: string | null;
  composition_sum: number | null;
  support_mode: SupportMode;
  support_basis: string;
  dext_origin: string;
  sensitivity_tags: string[];
  eligible: AnalysisId[];
  evidence: RecordEvidence;
}

export interface Stratum {
  analysis: string;
  fuel: Fuel;
  x: string;
  y: string;
  n: number;
  rho_spearman: number | null;
  note: string;
  n_values_in_x_ties: number;
  n_values_in_y_ties: number;
  sensitivity_rows: number[];
  rho_without_sensitivity_rows: number | null;
  evidence_class: string;
  psi_rows: number[];
  stratum: Record<string, string | number | null>;
}

export interface Provenance {
  source_id: string;
  doi: string;
  license: string;
  source_url: string;
  file_name: string;
  psi_file_version: string;
  psi_s3_version_id: string;
  raw_sha256: string;
  retrieved_at_utc: string;
  enrichment_file: string;
  enrichment_sha256: string;
  captions_sha256: string;
  analysis_summary_file: string;
  analysis_summary_sha256: string;
  report: string;
  report_url: string;
  report_pdf_sha256: string;
  audit_doc: string;
}

export interface LabDataset {
  dataset: string;
  dataset_version: string;
  analysis_version: string;
  synthetic: boolean;
  value_origin: string;
  provenance: Provenance;
  scope: {
    records: number;
    unique_flex_tests: number;
    unique_identifiers: number;
    nasa_stated_tests: number;
    table_ix_printed_rows: number;
    table_ix_rows_not_in_psi: string[];
  };
  units: Record<NumericField, string>;
  raw_headers: Record<NumericField, string>;
  rules: Record<string, string>;
  unknown_fields: string[];
  outcome_caveats: Record<Fuel, string>;
  records: FlexRecord[];
  strata: Stratum[];
}

export const FUELS: Fuel[] = ['Methanol', 'Heptane'];
export const SUPPORT_MODES: SupportMode[] = [
  'free_floating',
  'fiber_translated',
  'fiber_translation_not_stated',
  'conflicting_sources',
];
export const SUPPORT_LABEL: Record<SupportMode, string> = {
  free_floating: 'Free-floating',
  fiber_translated: 'Fiber, translated',
  fiber_translation_not_stated: 'Fiber, translation not stated',
  conflicting_sources: 'Conflicting sources',
  unknown: 'Unknown',
};
export const FAMILY_LABEL: Record<DiluentFamily, string> = {
  N2_only: 'N₂ only',
  CO2_added: 'CO₂ added',
  He_added: 'He added',
  CO2_and_He: 'CO₂ and He',
  unknown: 'Unknown',
};
export const FIELD_LABEL: Record<NumericField, string> = {
  ambient_pressure: 'Ambient pressure',
  ambient_oxygen_mole_fraction: 'O₂ mole fraction',
  ambient_nitrogen_mole_fraction: 'N₂ mole fraction',
  co2_mole_fraction: 'CO₂ mole fraction',
  ambient_helium_mole_fraction: 'He mole fraction',
  initial_droplet_diameter: 'Initial droplet diameter D₀',
  extinction_diameter: 'Visible flame extinction diameter',
  burning_rate_constant_mm2_s: 'Reported burning-rate constant K',
  burn_time_s: 'Burn time',
};

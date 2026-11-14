export type VerificationStatus =
  | 'NOT_YET_ACQUIRED'
  | 'CANDIDATE_ONLY'
  | 'ACQUIRED'
  | 'VERIFIED'
  | 'QUARANTINED'
  | 'RESOURCE_RECORDED'; // catalogue or index entry, never evidence on its own (docs/15 A.7)

export type CombustionRegime =
  | 'flex_droplet'
  | 'bass_ii_solid'
  | 'saffire_spacecraft_scale';

export interface SourceRecord {
  source_id: string;
  source_title: string;
  source_type: string;
  official_challenge_resource: boolean;
  source_url: string;
  doi: string;
  version_or_release: string;
  retrieved_at_utc: string;
  license: string;
  raw_file_path: string;
  sha256: string;
  verification_status: VerificationStatus;
  notes: string;
}

export interface RegimeRecord {
  regime: CombustionRegime;
  description: string;
  variables: string[];
}

export interface VariableSpec {
  symbol: string;
  name: string;
  unit: string;
  role: 'input' | 'output' | 'parameter';
}

export interface MethodReference {
  citation: string;
  doi: string | null;
}

export interface MethodCard {
  method_id: string;
  version: string;
  title: string;
  regimes: CombustionRegime[];
  formula: string;
  variables: VariableSpec[];
  references: MethodReference[];
  assumptions: string[];
  validity_limits: string[];
  required_inputs: string[];
  uncertainty_method: string;
  validation: string[];
  abstention_conditions: string[];
  status: string;
}

export interface ComparisonCondition {
  value: number;
  unit: string;
}

export interface ObservationDescriptor {
  investigation_id: string;
  regime: CombustionRegime;
  variable: string;
  unit: string;
  material_or_fuel?: string | null;
  apparatus?: string | null;
  conditions?: Record<string, ComparisonCondition>;
}

export interface ComparisonRequest {
  a: ObservationDescriptor;
  b: ObservationDescriptor;
}

export type ComparisonClass =
  | 'direct'
  | 'controlled_variation'
  | 'contextual'
  | 'not_comparable';

export interface ComparisonResult {
  classification: ComparisonClass;
  shared_axis_allowed: boolean;
  reasons: string[];
  held_constant: string[];
  differing: string[];
  unknown: string[];
}

// ---- Scientific RAG / Copilot (docs/16_rag_frontend_handoff.md) ----

export type Eligibility =
  | 'VERIFIED_ELIGIBLE'
  | 'PENDING_VERIFICATION'
  | 'ACQUIRED_BUT_EXCLUDED'
  | 'QUARANTINED'
  | 'UNREGISTERED';

export type EvidenceStatus = 'CLEAN' | 'QUALIFIED' | 'INVALID' | 'MISSING';

export type CopilotStatus = 'answered' | 'answered_with_ambiguity' | 'comparison_blocked' | 'abstained';

export type MeasurementVerification = 'platform' | 'loader_fallback' | 'unavailable' | 'none';

export interface RagSource {
  source_id: string;
  eligibility: Eligibility;
  usable_as_evidence: boolean;
  registry_status: string;
  decision_owner: string;
  decided_on: string;
}

export interface CitedMeasurement {
  measurement_id: string;
  run_id: string;
  variable: string;
  unit: string;
  evidence_status: EvidenceStatus;
  value: number | null; // null unless the value may be stated (CLEAN / QUALIFIED)
  quality_flags: string[];
  source_locator: string;
  provenance: string; // relative Data Platform route
}

export interface Citation {
  chunk_id: string;
  chunk_key: string;
  quote: string;
  source_id: string;
  source_title: string;
  source_url: string;
  doi: string;
  license: string;
  locator_text: string;
  artifact_id: string;
  source_artifact_sha256: string;
  verification_status: string;
  eligibility: Eligibility;
  quality_flags: string[];
  measurements: CitedMeasurement[];
}

export interface CopilotClaim {
  text: string;
  evidence_type: 'direct' | 'analogous';
  citations: Citation[];
  measurement_ids: string[];
  measurement_status: EvidenceStatus | null;
}

export interface CopilotResponse {
  status: CopilotStatus;
  answer: string;
  claims: CopilotClaim[];
  evidence: { direct: string[]; analogous: string[]; missing: string[]; flagged: string[] };
  abstention_reason: string | null;
  warnings: string[];
  measurement_verification: MeasurementVerification;
  source_eligibility: Record<string, string>;
  notice: string;
}

export interface MeasurementRef {
  measurement_id: string;
  variable: string;
  unit: string;
  evidence_status: EvidenceStatus;
  quality_flags: string[];
  statement: string;
}

export interface EvidenceChunk {
  chunk_id: string;
  chunk_key: string;
  source_id: string;
  source_title: string;
  locator_text: string;
  text: string;
  eligibility: Eligibility;
  verification_status: string;
  quality_flags: string[];
  measurements: MeasurementRef[];
}

export interface SearchHit {
  rank: number;
  score: number;
  chunk: EvidenceChunk;
}

export interface SearchResponse {
  query: string;
  mode: string;
  hits: SearchHit[];
  warnings: string[];
}

// ---- Scientific Data Platform (/runs, /measurements, /provenance, /data-platform/status) ----

export interface RunSummary {
  run_id: string;
  investigation_id: string;
  source_row: number;
  source_identifier: string;
  source_record_key: string | null;
  combustion_regime: string;
  material_or_fuel: string | null;
  test_date: string | null;
  test_date_raw: string;
  test_time_gmt_raw: string;
  end_mode: string | null;
  quality_flags: string[];
  derived_attributes: Record<string, unknown>;
  source_locator: string;
}

export interface ArtifactRecord {
  artifact_id: string;
  investigation_id: string;
  artifact_kind: string;
  file_name: string;
  relative_path: string;
  media_type: string | null;
  text_encoding: string | null;
  byte_size: number;
  sha256: string;
  source_url: string;
  source_version: string | null;
  license_id: string | null;
  retrieved_at: string;
}

export interface MeasurementRecord {
  measurement_id: string;
  run_id: string;
  variable_name: string;
  role: string;
  value: number | null;
  value_status: string;
  original_value_text: string;
  unit: string;
  measured_or_derived: string;
  usable_for_analysis: boolean;
  quality_flags: string[];
  attributes: Record<string, unknown>;
  uncertainty_value: number | null;
  uncertainty_type: string | null;
  coverage_factor: number | null;
  source_column: string;
  source_locator: string;
}

export interface RunDetail extends RunSummary {
  artifact: ArtifactRecord;
  measurements: MeasurementRecord[];
}

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceCell {
  file_name: string;
  source_row: number;
  source_column: string;
  original_value_text: string;
  original_unit_label: string | null;
  platform_unit: string;
  unit_evidence: string | null;
  source_locator: string;
}

export interface ProvenanceRecord {
  measurement: MeasurementRecord;
  source_cell: SourceCell;
  run: RunSummary;
  investigation: {
    investigation_id: string;
    title: string;
    acronym: string | null;
    combustion_regime: string;
    source_repository: string;
    source_url: string;
    doi: string | null;
    license_id: string | null;
    research_area: string | null;
    official_challenge_resource: boolean;
    registry_status: string;
  };
  artifact: ArtifactRecord;
  extraction: {
    extraction_run_id: string;
    extractor_name: string;
    extractor_version: string;
    inputs_json: Record<string, unknown>;
    parameters_json: Record<string, unknown>;
    code_revision: string | null;
    run_count: number;
    measurement_count: number;
    first_loaded_at: string;
    last_loaded_at: string;
  };
  extraction_method: string;
  how_to_verify: string;
}

export interface DataPlatformStatus {
  database_configured: boolean;
  database_reachable: boolean;
  schema_revision: string | null;
  expected_schema_revision: string;
  investigations_loaded: string[];
  official_challenge_resource_loaded: boolean;
  runs: number;
  measurements: number;
  detail: string | null;
}

// ---- Physics-Informed Analysis (/physics/d2-consistency, /physics/oxygen-effect) ----

export interface D2FuelSummary {
  n: number;
  median: number;
  median_ci95: [number, number] | null;
  q1: number;
  q3: number;
  min: number;
  max: number;
  tukey_fences: [number, number];
  share_of_intervals_containing_1: number;
}

export interface D2RunResult {
  run_id: string;
  experiment_id: string;
  fuel: string;
  d0_mm: number;
  dext_mm: number;
  k_mm2_s: number;
  burn_time_s: number;
  t_d2_s: number;
  ratio: number;
  ratio_interval: [number, number];
  review_flag: string | null;
}

export interface D2ConsistencyResponse {
  analysis: 'd2_consistency';
  analysis_version: string;
  equation: string;
  value_origin: string;
  n_runs: number;
  excluded: Record<string, number>;
  by_fuel: Record<string, D2FuelSummary>;
  flagged_for_review: string[];
  runs: D2RunResult[];
  uncertainty: {
    per_run: string;
    summary: string;
  };
  limitations: string[];
}

export interface RegressionCoefficient {
  estimate: number;
  se_hc3: number;
  ci95: [number, number];
  p_value: number;
}

export interface OlsModelResult {
  intercept: RegressionCoefficient;
  x_o2: RegressionCoefficient;
  d0_mm?: RegressionCoefficient;
  r_squared: number;
  dof_resid: number;
}

export interface OxygenStratumResult {
  fuel: string;
  pressure_cluster: string | null;
  support_mode: string;
  n: number;
  x_o2_range: [number, number];
  n_distinct_o2: number;
  run_ids: string[];
  computable: boolean;
  abstention_reason?: string;
  model_k_on_o2?: OlsModelResult;
  sensitivity_k_on_o2_and_d0?: OlsModelResult | null;
  spearman_o2_k?: number | null;
}

export interface OxygenEffectResponse {
  analysis: 'oxygen_effect';
  analysis_version: string;
  model: string;
  units: Record<string, string>;
  value_origin: string;
  strata_held_fixed: string[];
  excluded: Record<string, number>;
  strata: OxygenStratumResult[];
  limitations: string[];
}

// ---- Flame Vision Metrology (/vision/method, /vision/evaluation, /vision/tests) ----

export interface VisionThresholdSensitivity {
  '0.4': number;
  '0.5': number;
  '0.6': number;
}

export interface VisionEvalTest {
  test_point: string;
  run_id: string;
  fuel: string;
  test_end: string;
  computable: boolean;
  // Present when computable === true
  fit_frames?: number;
  fit_r_squared?: number;
  fit_window_coverage?: number;
  vision_k_over_d0sq_per_s?: number;
  vision_rel_uncertainty_1sigma?: number;
  threshold_sensitivity?: VisionThresholdSensitivity;
  nasa_k_over_d0sq_per_s?: number;
  relative_difference?: number;
  implied_mm_per_px_from_nasa_d0?: number;
  // Present when computable === false
  abstention_reason?: string;
}

export interface VisionEvaluation {
  method_id: string;
  method_version: string;
  tests: VisionEvalTest[];
  n_tests: number;
  n_computable: number;
  n_abstained: number;
  relative_difference_mean: number;
  relative_difference_range: [number, number];
  implied_scale_range_mm_per_px: [number, number];
  verdict: string;
}

export interface VisionFitResult {
  slope: number;
  intercept: number;
  slope_se: number;
  slope_ci95: [number, number];
  r_squared: number;
  n: number;
  t_start: number;
  t_end: number;
  slope_px2_per_s: number;
}

export interface VisionNasaReference {
  run_id: string;
  flex_identifier: string;
  fuel: string;
  test_end: string;
  reported_k_mm2_per_s: number;
  reported_d0_mm: number;
  reported_extinction_diameter_mm: number | null;
  reported_burn_time_s: number;
  reported_k_over_d0sq_per_s: number;
  reported_dext_over_d0: number | null;
  value_origin: string;
}

export interface VisionComparison {
  nasa_k_over_d0sq_per_s: number;
  vision_k_over_d0sq_per_s: number;
  relative_difference: number;
  nasa_dext_over_d0: number | null;
  implied_mm_per_px_from_nasa_d0: number;
  implied_scale_note: string;
  vision_regime_break_diameter_ratio_proxy: number;
  note: string;
}

export interface VisionTestSummary {
  test_point: string;
  method: {
    method_id: string;
    version: string;
    status: string;
  };
  camera?: Record<string, string>;
  physical_units: null;
  physical_units_reason: string;
  computable?: boolean;
  abstention_reason?: string;
  results?: {
    d0_px: number;
    d0_mad_px: number;
    d0_frames: number;
    fit_window_coverage: number;
    fit: VisionFitResult;
    k_px2_per_s: number;
    k_over_d0sq_per_s: number;
    k_over_d0sq_rel_uncertainty_1sigma: number;
    k_over_d0sq_first_half_per_s: number;
    k_over_d0sq_second_half_per_s: number;
    regime_break_t_s: number;
    regime_break_diameter_ratio: number;
    windows_s: {
      d0: [number, number];
      excluded_igniters: [number, number];
      fit: [number, number];
    };
    threshold_sensitivity_k_over_d0sq: VisionThresholdSensitivity;
    frame_status_counts: Record<string, number>;
    measured_frames_with_flags: number;
    segmentation_params: {
      threshold_fraction: number;
      min_area_px: number;
      max_aspect_ratio: number;
      min_circularity: number;
      border_margin_px: number;
    };
  };
  nasa_reference: VisionNasaReference;
  comparison?: VisionComparison;
  provenance: Array<{
    source_id: string;
    test_point: string;
    role: string;
    file_name: string;
    relative_path: string;
    byte_size: string;
    sha256: string;
    source_url: string;
    license: string;
    retrieved_at_utc: string;
  }>;
  generated_at_utc: string;
}

export interface VisionFrame {
  frame: string;
  t_s: number | null;
  status: string;
  diameter_px: number | null;
  area_px: number | null;
  circularity: number | null;
  centroid_x_px: number | null;
  centroid_y_px: number | null;
  candidates: number | null;
  flags: string[];
}


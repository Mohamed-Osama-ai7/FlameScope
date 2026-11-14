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

export type VerificationStatus =
  | 'NOT_YET_ACQUIRED'
  | 'CANDIDATE_ONLY'
  | 'ACQUIRED'
  | 'VERIFIED'
  | 'QUARANTINED';

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

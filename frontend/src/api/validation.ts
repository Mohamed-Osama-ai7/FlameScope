import type {
  CombustionRegime,
  ComparisonClass,
  ComparisonResult,
  MethodCard,
  RegimeRecord,
  SourceRecord,
  VerificationStatus,
} from './contracts';

const VERIFICATION_STATUSES: VerificationStatus[] = [
  'NOT_YET_ACQUIRED', 'CANDIDATE_ONLY', 'ACQUIRED', 'VERIFIED', 'QUARANTINED', 'RESOURCE_RECORDED',
];
const REGIMES: CombustionRegime[] = [
  'flex_droplet', 'bass_ii_solid', 'saffire_spacecraft_scale',
];
const COMPARISON_CLASSES: ComparisonClass[] = [
  'direct', 'controlled_variation', 'contextual', 'not_comparable',
];

function isRecord(payload: unknown): payload is Record<string, unknown> {
  return typeof payload === 'object' && payload !== null && !Array.isArray(payload);
}

function isStringList(payload: unknown): payload is string[] {
  return Array.isArray(payload) && payload.every((entry) => typeof entry === 'string');
}

function isRegime(payload: unknown): payload is CombustionRegime {
  return typeof payload === 'string' && REGIMES.includes(payload as CombustionRegime);
}

export function parseSource(payload: unknown): SourceRecord {
  if (!isRecord(payload)) throw new Error('Source record must be an object.');
  const stringFields = [
    'source_id', 'source_title', 'source_type', 'source_url', 'doi', 'version_or_release',
    'retrieved_at_utc', 'license', 'raw_file_path', 'sha256', 'notes',
  ] as const;
  if (!stringFields.every((field) => typeof payload[field] === 'string')) {
    throw new Error('Source record contains invalid text fields.');
  }
  if (typeof payload.official_challenge_resource !== 'boolean') {
    throw new Error('Source record has an invalid challenge-resource flag.');
  }
  if (!VERIFICATION_STATUSES.includes(payload.verification_status as VerificationStatus)) {
    throw new Error('Source record has an unknown verification status.');
  }
  return payload as unknown as SourceRecord;
}

export function parseRegime(payload: unknown): RegimeRecord {
  if (!isRecord(payload) || !isRegime(payload.regime)
    || typeof payload.description !== 'string' || !isStringList(payload.variables)) {
    throw new Error('Regime response has an invalid shape.');
  }
  return payload as unknown as RegimeRecord;
}

function isMethodVariable(payload: unknown): boolean {
  return isRecord(payload)
    && typeof payload.symbol === 'string'
    && typeof payload.name === 'string'
    && typeof payload.unit === 'string'
    && ['input', 'output', 'parameter'].includes(String(payload.role));
}

function isReference(payload: unknown): boolean {
  return isRecord(payload)
    && typeof payload.citation === 'string'
    && (typeof payload.doi === 'string' || payload.doi === null);
}

export function parseMethod(payload: unknown): MethodCard {
  if (!isRecord(payload)) throw new Error('Method card must be an object.');
  const textFields = [
    'method_id', 'version', 'title', 'formula', 'uncertainty_method', 'status',
  ] as const;
  const listFields = [
    'assumptions', 'validity_limits', 'required_inputs', 'validation', 'abstention_conditions',
  ] as const;
  if (!textFields.every((field) => typeof payload[field] === 'string')
    || !listFields.every((field) => isStringList(payload[field]))
    || !Array.isArray(payload.regimes) || !payload.regimes.every(isRegime)
    || !Array.isArray(payload.variables) || !payload.variables.every(isMethodVariable)
    || !Array.isArray(payload.references) || !payload.references.every(isReference)) {
    throw new Error('Method card response has an invalid shape.');
  }
  return payload as unknown as MethodCard;
}

export function parseComparison(payload: unknown): ComparisonResult {
  if (!isRecord(payload)
    || !COMPARISON_CLASSES.includes(payload.classification as ComparisonClass)
    || typeof payload.shared_axis_allowed !== 'boolean'
    || !['reasons', 'held_constant', 'differing', 'unknown']
      .every((field) => isStringList(payload[field]))) {
    throw new Error('Comparison response has an invalid shape.');
  }
  return payload as unknown as ComparisonResult;
}

export function parseList<T>(payload: unknown, parseEntry: (entry: unknown) => T): T[] {
  if (!Array.isArray(payload)) throw new Error('API response must be a list.');
  return payload.map(parseEntry);
}

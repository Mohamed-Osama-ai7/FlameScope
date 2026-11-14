import type {
  Citation,
  CitedMeasurement,
  CopilotClaim,
  CopilotResponse,
  CopilotStatus,
  Eligibility,
  EvidenceChunk,
  EvidenceStatus,
  MeasurementRef,
  MeasurementVerification,
  RagSource,
  SearchResponse,
} from './contracts';

// Strict parsing: an unknown status is rejected rather than rendered with the wrong meaning.
const ELIGIBILITY: Eligibility[] = [
  'VERIFIED_ELIGIBLE', 'PENDING_VERIFICATION', 'ACQUIRED_BUT_EXCLUDED', 'QUARANTINED', 'UNREGISTERED',
];
const EVIDENCE_STATUS: EvidenceStatus[] = ['CLEAN', 'QUALIFIED', 'INVALID', 'MISSING'];
const COPILOT_STATUS: CopilotStatus[] = ['answered', 'answered_with_ambiguity', 'comparison_blocked', 'abstained'];
const VERIFICATION: MeasurementVerification[] = ['platform', 'loader_fallback', 'unavailable', 'none'];

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === 'string';
const strList = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr);
const strs = (o: Obj, fields: readonly string[]) => fields.every((f) => isStr(o[f]));

function fail(what: string): never {
  throw new Error(`${what} response has an invalid shape.`);
}

export function parseRagSource(p: unknown): RagSource {
  if (!isObj(p) || !strs(p, ['source_id', 'registry_status', 'decision_owner', 'decided_on'])
    || !ELIGIBILITY.includes(p.eligibility as Eligibility) || typeof p.usable_as_evidence !== 'boolean') {
    fail('Source eligibility');
  }
  return p as unknown as RagSource;
}

function parseCitedMeasurement(p: unknown): CitedMeasurement {
  if (!isObj(p) || !strs(p, ['measurement_id', 'run_id', 'variable', 'unit', 'source_locator', 'provenance'])
    || !EVIDENCE_STATUS.includes(p.evidence_status as EvidenceStatus) || !strList(p.quality_flags)
    || !(p.value === null || typeof p.value === 'number')) {
    fail('Cited measurement');
  }
  // a value must never accompany an invalid or missing cell
  if ((p.evidence_status === 'INVALID' || p.evidence_status === 'MISSING') && p.value !== null) {
    fail('Cited measurement');
  }
  return p as unknown as CitedMeasurement;
}

function parseCitation(p: unknown): Citation {
  const text = ['chunk_id', 'chunk_key', 'quote', 'source_id', 'source_title', 'source_url', 'doi', 'license',
    'locator_text', 'artifact_id', 'source_artifact_sha256', 'verification_status'] as const;
  if (!isObj(p) || !strs(p, text) || !ELIGIBILITY.includes(p.eligibility as Eligibility)
    || !strList(p.quality_flags) || !Array.isArray(p.measurements)) {
    fail('Citation');
  }
  p.measurements.forEach(parseCitedMeasurement);
  return p as unknown as Citation;
}

function parseClaim(p: unknown): CopilotClaim {
  if (!isObj(p) || !isStr(p.text) || !['direct', 'analogous'].includes(String(p.evidence_type))
    || !Array.isArray(p.citations) || !strList(p.measurement_ids)
    || !(p.measurement_status === null || EVIDENCE_STATUS.includes(p.measurement_status as EvidenceStatus))) {
    fail('Copilot claim');
  }
  p.citations.forEach(parseCitation);
  return p as unknown as CopilotClaim;
}

export function parseCopilotResponse(p: unknown): CopilotResponse {
  if (!isObj(p) || !COPILOT_STATUS.includes(p.status as CopilotStatus) || !isStr(p.answer)
    || !Array.isArray(p.claims) || !isObj(p.evidence) || !strList(p.warnings) || !isStr(p.notice)
    || !(p.abstention_reason === null || isStr(p.abstention_reason))
    || !VERIFICATION.includes(p.measurement_verification as MeasurementVerification)
    || !isObj(p.source_eligibility)
    || !['direct', 'analogous', 'missing', 'flagged'].every((k) => strList((p.evidence as Obj)[k]))) {
    fail('Copilot');
  }
  p.claims.forEach(parseClaim);
  return p as unknown as CopilotResponse;
}

function parseMeasurementRef(p: unknown): MeasurementRef {
  if (!isObj(p) || !strs(p, ['measurement_id', 'variable', 'unit', 'statement'])
    || !EVIDENCE_STATUS.includes(p.evidence_status as EvidenceStatus) || !strList(p.quality_flags)) {
    fail('Measurement reference');
  }
  return p as unknown as MeasurementRef;
}

function parseChunk(p: unknown): EvidenceChunk {
  if (!isObj(p) || !strs(p, ['chunk_id', 'chunk_key', 'source_id', 'source_title', 'locator_text', 'text',
    'verification_status']) || !ELIGIBILITY.includes(p.eligibility as Eligibility)
    || !strList(p.quality_flags) || !Array.isArray(p.measurements)) {
    fail('Evidence chunk');
  }
  p.measurements.forEach(parseMeasurementRef);
  return p as unknown as EvidenceChunk;
}

export function parseSearchResponse(p: unknown): SearchResponse {
  if (!isObj(p) || !isStr(p.query) || !isStr(p.mode) || !Array.isArray(p.hits) || !strList(p.warnings)) {
    fail('Evidence search');
  }
  for (const h of p.hits) {
    if (!isObj(h) || typeof h.rank !== 'number' || typeof h.score !== 'number') fail('Evidence search');
    parseChunk(h.chunk);
  }
  return p as unknown as SearchResponse;
}

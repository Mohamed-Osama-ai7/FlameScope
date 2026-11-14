import type {
  ArtifactRecord,
  DataPlatformStatus,
  MeasurementRecord,
  PaginatedResult,
  ProvenanceRecord,
  RunDetail,
  RunSummary,
  SourceCell,
} from './contracts';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === 'string';
const isNum = (v: unknown): v is number => typeof v === 'number';
const isBool = (v: unknown): v is boolean => typeof v === 'boolean';
const strList = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr);

function fail(what: string): never {
  throw new Error(`${what} response has an invalid shape.`);
}

export function parseRunSummary(p: unknown): RunSummary {
  if (!isObj(p)) fail('Run summary');
  if (!isStr(p.run_id) || !isStr(p.investigation_id) || !isNum(p.source_row)
    || !isStr(p.source_identifier) || !isStr(p.combustion_regime)
    || !isStr(p.test_date_raw) || !isStr(p.test_time_gmt_raw)
    || !isStr(p.source_locator) || !strList(p.quality_flags)
    || !isObj(p.derived_attributes)) {
    fail('Run summary');
  }
  return p as unknown as RunSummary;
}

export function parseArtifactRecord(p: unknown): ArtifactRecord {
  if (!isObj(p)) fail('Artifact record');
  if (!isStr(p.artifact_id) || !isStr(p.investigation_id) || !isStr(p.artifact_kind)
    || !isStr(p.file_name) || !isStr(p.relative_path) || !isNum(p.byte_size)
    || !isStr(p.sha256) || !isStr(p.source_url) || !isStr(p.retrieved_at)) {
    fail('Artifact record');
  }
  return p as unknown as ArtifactRecord;
}

export function parseMeasurementRecord(p: unknown): MeasurementRecord {
  if (!isObj(p)) fail('Measurement record');
  if (!isStr(p.measurement_id) || !isStr(p.run_id) || !isStr(p.variable_name)
    || !isStr(p.role) || !isStr(p.original_value_text) || !isStr(p.unit)
    || !isStr(p.measured_or_derived) || !isBool(p.usable_for_analysis)
    || !strList(p.quality_flags) || !isStr(p.source_column) || !isStr(p.source_locator)) {
    fail('Measurement record');
  }
  if (p.value !== null && !isNum(p.value)) fail('Measurement record value');
  return p as unknown as MeasurementRecord;
}

export function parseRunDetail(p: unknown): RunDetail {
  const summary = parseRunSummary(p);
  if (!isObj(p) || !Array.isArray(p.measurements) || !isObj(p.artifact)) {
    fail('Run detail');
  }
  const artifact = parseArtifactRecord(p.artifact);
  const measurements = p.measurements.map(parseMeasurementRecord);
  return { ...summary, artifact, measurements };
}

export function parsePaginatedRuns(p: unknown): PaginatedResult<RunSummary> {
  if (!isObj(p) || !Array.isArray(p.items) || !isNum(p.total) || !isNum(p.limit) || !isNum(p.offset)) {
    fail('Paginated runs');
  }
  return {
    items: p.items.map(parseRunSummary),
    total: p.total,
    limit: p.limit,
    offset: p.offset,
  };
}

export function parsePaginatedMeasurements(p: unknown): PaginatedResult<MeasurementRecord> {
  if (!isObj(p) || !Array.isArray(p.items) || !isNum(p.total) || !isNum(p.limit) || !isNum(p.offset)) {
    fail('Paginated measurements');
  }
  return {
    items: p.items.map(parseMeasurementRecord),
    total: p.total,
    limit: p.limit,
    offset: p.offset,
  };
}

export function parseProvenanceRecord(p: unknown): ProvenanceRecord {
  if (!isObj(p) || !isObj(p.measurement) || !isObj(p.source_cell)
    || !isObj(p.run) || !isObj(p.investigation) || !isObj(p.artifact)
    || !isObj(p.extraction) || !isStr(p.extraction_method) || !isStr(p.how_to_verify)) {
    fail('Provenance record');
  }
  const measurement = parseMeasurementRecord(p.measurement);
  const run = parseRunSummary(p.run);
  const artifact = parseArtifactRecord(p.artifact);
  const sourceCell = p.source_cell as unknown as SourceCell;
  return p as unknown as ProvenanceRecord;
}

export function parseDataPlatformStatus(p: unknown): DataPlatformStatus {
  if (!isObj(p) || !isBool(p.database_configured) || !isBool(p.database_reachable)
    || !isNum(p.runs) || !isNum(p.measurements) || !strList(p.investigations_loaded)) {
    fail('Data platform status');
  }
  return p as unknown as DataPlatformStatus;
}

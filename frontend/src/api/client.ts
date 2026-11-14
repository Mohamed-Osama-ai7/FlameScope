import type {
  ComparisonRequest,
  ComparisonResult,
  CopilotResponse,
  DataPlatformStatus,
  MeasurementRecord,
  MethodCard,
  PaginatedResult,
  ProvenanceRecord,
  RagSource,
  RunDetail,
  RunSummary,
  SearchResponse,
  RegimeRecord,
  SourceRecord,
} from './contracts';
import {
  parseDataPlatformStatus,
  parseMeasurementRecord,
  parsePaginatedMeasurements,
  parsePaginatedRuns,
  parseProvenanceRecord,
  parseRunDetail,
} from './dataPlatformValidation';
import { parseCopilotResponse, parseRagSource, parseSearchResponse } from './ragValidation';
import { parseComparison, parseList, parseMethod, parseRegime, parseSource } from './validation';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000')
  .replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === 'string') return payload;
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = payload.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      // FastAPI 422: [{loc, msg, type}]
      return detail.map((d) => (typeof d === 'object' && d !== null && 'msg' in d ? String(d.msg) : String(d)))
        .join('; ');
    }
    // RAG 403 for an ineligible chunk: {eligibility, message, ...}
    if (typeof detail === 'object' && detail !== null && 'message' in detail) {
      const eligibility = 'eligibility' in detail ? ` (${String(detail.eligibility)})` : '';
      return `${String(detail.message)}${eligibility}`;
    }
  }
  return fallback;
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, init);
  const responseText = await response.text();
  let payload: unknown;
  try {
    payload = responseText ? JSON.parse(responseText) as unknown : undefined;
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    if (!response.ok) throw new ApiError(response.statusText, response.status);
    throw new ApiError('API returned invalid JSON.', response.status);
  }
  if (!response.ok) {
    throw new ApiError(errorMessage(payload, response.statusText), response.status);
  }
  return payload;
}

export const api = {
  async listSources(): Promise<SourceRecord[]> {
    const payload = await requestJson('/sources');
    return parseList(payload, parseSource);
  },
  async listRegimes(): Promise<RegimeRecord[]> {
    const payload = await requestJson('/regimes');
    return parseList(payload, parseRegime);
  },
  async listMethods(): Promise<MethodCard[]> {
    const payload = await requestJson('/methods');
    return parseList(payload, parseMethod);
  },
  async validateComparison(request: ComparisonRequest, signal?: AbortSignal): Promise<ComparisonResult> {
    const payload = await requestJson('/comparisons/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });
    return parseComparison(payload);
  },
  // ---- Scientific RAG / Copilot (public routes only; ineligible evidence is never requested) ----
  async listEvidenceSources(): Promise<RagSource[]> {
    return parseList(await requestJson('/rag/sources'), parseRagSource);
  },
  async searchEvidence(query: string, signal?: AbortSignal): Promise<SearchResponse> {
    const payload = await requestJson('/rag/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: 8 }),
      signal,
    });
    return parseSearchResponse(payload);
  },
  async askCopilot(question: string, signal?: AbortSignal): Promise<CopilotResponse> {
    const payload = await requestJson('/copilot/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    });
    return parseCopilotResponse(payload);
  },
  // ---- Scientific Data Platform (/runs, /measurements, /provenance, /data-platform/status) ----
  async getDataPlatformStatus(): Promise<DataPlatformStatus> {
    return parseDataPlatformStatus(await requestJson('/data-platform/status'));
  },
  async listRuns(params?: {
    investigation?: string;
    fuel?: string;
    source_record_key?: string;
    limit?: number;
    offset?: number;
  }, signal?: AbortSignal): Promise<PaginatedResult<RunSummary>> {
    const query = new URLSearchParams();
    if (params?.investigation) query.set('investigation', params.investigation);
    if (params?.fuel) query.set('fuel', params.fuel);
    if (params?.source_record_key) query.set('source_record_key', params.source_record_key);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    const qs = query.toString();
    const payload = await requestJson(`/runs${qs ? `?${qs}` : ''}`, { signal });
    return parsePaginatedRuns(payload);
  },
  async getRun(runId: string, signal?: AbortSignal): Promise<RunDetail> {
    const payload = await requestJson(`/runs/${encodeURIComponent(runId)}`, { signal });
    return parseRunDetail(payload);
  },
  async listMeasurements(params?: {
    investigation?: string;
    run_id?: string;
    variable?: string;
    usable_only?: boolean;
    limit?: number;
    offset?: number;
  }, signal?: AbortSignal): Promise<PaginatedResult<MeasurementRecord>> {
    const query = new URLSearchParams();
    if (params?.investigation) query.set('investigation', params.investigation);
    if (params?.run_id) query.set('run_id', params.run_id);
    if (params?.variable) query.set('variable', params.variable);
    if (params?.usable_only !== undefined) query.set('usable_only', String(params.usable_only));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));
    const qs = query.toString();
    const payload = await requestJson(`/measurements${qs ? `?${qs}` : ''}`, { signal });
    return parsePaginatedMeasurements(payload);
  },
  async getMeasurement(measurementId: string, signal?: AbortSignal): Promise<MeasurementRecord> {
    const payload = await requestJson(`/measurements/${encodeURIComponent(measurementId)}`, { signal });
    return parseMeasurementRecord(payload);
  },
  async getMeasurementProvenance(measurementId: string, signal?: AbortSignal): Promise<ProvenanceRecord> {
    const payload = await requestJson(`/measurements/${encodeURIComponent(measurementId)}/provenance`, { signal });
    return parseProvenanceRecord(payload);
  },
};

/** Absolute URL of a Data Platform route returned by the RAG API (e.g. a measurement's provenance). */
export function apiUrl(relativePath: string): string {
  return `${API_BASE_URL}${relativePath.startsWith('/') ? '' : '/'}${relativePath}`;
}

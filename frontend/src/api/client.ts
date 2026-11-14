import type {
  ComparisonRequest,
  ComparisonResult,
  CopilotResponse,
  D2ConsistencyResponse,
  DataPlatformStatus,
  MeasurementRecord,
  MethodCard,
  OxygenEffectResponse,
  PaginatedResult,
  ProvenanceRecord,
  RagSource,
  RunDetail,
  RunSummary,
  SearchResponse,
  RegimeRecord,
  SourceRecord,
  VisionEvaluation,
  VisionFrame,
  VisionTestSummary,
} from './contracts';
import {
  parseDataPlatformStatus,
  parseMeasurementRecord,
  parsePaginatedMeasurements,
  parsePaginatedRuns,
  parseProvenanceRecord,
  parseRunDetail,
} from './dataPlatformValidation';
import { parseD2Consistency, parseOxygenEffect } from './physicsValidation';
import { parseCopilotResponse, parseRagSource, parseSearchResponse } from './ragValidation';
import { parseComparison, parseList, parseMethod, parseRegime, parseSource } from './validation';
import { parseVisionEvaluation, parseVisionFrameList, parseVisionTestSummary } from './visionValidation';

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
  // ---- Physics-Informed Analysis (/physics/d2-consistency, /physics/oxygen-effect) ----
  async getD2Consistency(params?: {
    fuel?: 'Methanol' | 'Heptane';
    diameter_halfwidth_mm?: number;
  }, signal?: AbortSignal): Promise<D2ConsistencyResponse> {
    const query = new URLSearchParams();
    if (params?.fuel) query.set('fuel', params.fuel);
    if (params?.diameter_halfwidth_mm !== undefined) {
      query.set('diameter_halfwidth_mm', String(params.diameter_halfwidth_mm));
    }
    const qs = query.toString();
    const payload = await requestJson(`/physics/d2-consistency${qs ? `?${qs}` : ''}`, { signal });
    return parseD2Consistency(payload);
  },
  async getOxygenEffect(params?: {
    fuel?: 'Methanol' | 'Heptane';
  }, signal?: AbortSignal): Promise<OxygenEffectResponse> {
    const query = new URLSearchParams();
    if (params?.fuel) query.set('fuel', params.fuel);
    const qs = query.toString();
    const payload = await requestJson(`/physics/oxygen-effect${qs ? `?${qs}` : ''}`, { signal });
    return parseOxygenEffect(payload);
  },
  // ---- Flame Vision & Metrology (/vision/method, /vision/evaluation, /vision/tests) ----
  async getVisionMethod(signal?: AbortSignal): Promise<MethodCard> {
    const payload = await requestJson('/vision/method', { signal });
    return parseMethod(payload);
  },
  async getVisionEvaluation(signal?: AbortSignal): Promise<VisionEvaluation> {
    const payload = await requestJson('/vision/evaluation', { signal });
    return parseVisionEvaluation(payload);
  },
  async getVisionTest(testPoint: string, signal?: AbortSignal): Promise<VisionTestSummary> {
    const payload = await requestJson(`/vision/tests/${encodeURIComponent(testPoint)}`, { signal });
    return parseVisionTestSummary(payload);
  },
  async getVisionTestSeries(testPoint: string, signal?: AbortSignal): Promise<VisionFrame[]> {
    const payload = await requestJson(`/vision/tests/${encodeURIComponent(testPoint)}/series`, { signal });
    return parseVisionFrameList(payload);
  },
};

/** Load the precomputed verified physics baseline when the live backend is offline. */
export async function loadOfflinePhysicsBaseline(): Promise<{
  d2_consistency: D2ConsistencyResponse;
  oxygen_effect: OxygenEffectResponse;
}> {
  const base = import.meta.env.BASE_URL ?? '/';
  const prefix = base.endsWith('/') ? base : `${base}/`;
  const res = await fetch(`${prefix}data/physics_baseline_v0.1.1.json`);
  if (!res.ok) throw new Error(`Failed to load offline physics baseline: ${res.statusText}`);
  const data = (await res.json()) as { d2_consistency: unknown; oxygen_effect: unknown };
  return {
    d2_consistency: parseD2Consistency(data.d2_consistency),
    oxygen_effect: parseOxygenEffect(data.oxygen_effect),
  };
}

export interface OfflineVisionBaseline {
  evaluation: VisionEvaluation;
  tests: Record<string, VisionTestSummary>;
  series: Record<string, VisionFrame[]>;
  method: MethodCard;
}

/** Load the precomputed verified flame vision baseline when the live backend is offline. */
export async function loadOfflineVisionBaseline(): Promise<OfflineVisionBaseline> {
  const base = import.meta.env.BASE_URL ?? '/';
  const prefix = base.endsWith('/') ? base : `${base}/`;
  const res = await fetch(`${prefix}data/flame_vision_baseline_v1.0.0.json`);
  if (!res.ok) throw new Error(`Failed to load offline vision baseline: ${res.statusText}`);
  const data = (await res.json()) as {
    evaluation: unknown;
    tests: Record<string, unknown>;
    series: Record<string, unknown>;
    method: unknown;
  };
  const tests: Record<string, VisionTestSummary> = {};
  for (const [k, v] of Object.entries(data.tests)) {
    tests[k] = parseVisionTestSummary(v);
  }
  const series: Record<string, VisionFrame[]> = {};
  for (const [k, v] of Object.entries(data.series)) {
    series[k] = parseVisionFrameList(v);
  }
  return {
    evaluation: parseVisionEvaluation(data.evaluation),
    tests,
    series,
    method: parseMethod(data.method),
  };
}

/** Absolute URL of a Data Platform route returned by the RAG API (e.g. a measurement's provenance). */
export function apiUrl(relativePath: string): string {
  return `${API_BASE_URL}${relativePath.startsWith('/') ? '' : '/'}${relativePath}`;
}

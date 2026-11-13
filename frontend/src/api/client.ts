import type {
  ComparisonRequest,
  ComparisonResult,
  MethodCard,
  RegimeRecord,
  SourceRecord,
} from './contracts';
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
    if (Array.isArray(detail)) return detail.map(String).join('; ');
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
};

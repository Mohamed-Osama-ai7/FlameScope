import { readFileSync } from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, apiUrl } from '../../src/api/client';
import { parseCopilotResponse, parseRagSource, parseSearchResponse } from '../../src/api/ragValidation';
import { parseList, parseSource } from '../../src/api/validation';

// Fixtures are verbatim responses captured from the merged backend (RAG + Data Platform, SQLite platform DB)
// on 2026-11-14; see tests/fixtures/api/README.md.
const fixture = (name: string): unknown =>
  JSON.parse(readFileSync(new URL(`../fixtures/api/${name}.json`, import.meta.url), 'utf8'));

afterEach(() => vi.unstubAllGlobals());

function mockResponse(payload: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status })));
}

describe('source registry (RESOURCE_RECORDED)', () => {
  it('parses the real /sources response including the catalogue entry', () => {
    const sources = parseList(fixture('sources'), parseSource);
    const statuses = Object.fromEntries(sources.map((s) => [s.source_id, s.verification_status]));
    expect(statuses['CHALLENGE-RESOURCE-01']).toBe('RESOURCE_RECORDED');
    expect(statuses['PSI-98']).toBe('QUARANTINED');
  });

  it('parses source eligibility without promoting any source', () => {
    const rows = parseList(fixture('rag_sources'), parseRagSource);
    const by = Object.fromEntries(rows.map((r) => [r.source_id, r]));
    expect(by['PSI-69'].eligibility).toBe('PENDING_VERIFICATION');
    expect(by['PSI-25']).toMatchObject({ eligibility: 'ACQUIRED_BUT_EXCLUDED', usable_as_evidence: false });
    expect(by['PSI-98']).toMatchObject({ eligibility: 'QUARANTINED', usable_as_evidence: false });
    expect(by['NASA-TP-2015-216046']).toMatchObject({ eligibility: 'UNREGISTERED', usable_as_evidence: false });
  });
});

describe('Copilot responses', () => {
  it.each([
    ['clean', 'CLEAN'],
    ['invalid', 'INVALID'],
    ['missing', 'MISSING'],
    ['qualified', 'QUALIFIED'],
  ])('parses the real %s measurement answer', (name, status) => {
    const r = parseCopilotResponse(fixture(`copilot_${name}`));
    expect(r.status).toBe('answered');
    const claim = r.claims.find((c) => c.measurement_status === status);
    expect(claim).toBeDefined();
    const m = claim!.citations[0].measurements[0];
    expect(m.evidence_status).toBe(status);
    if (status === 'INVALID' || status === 'MISSING') expect(m.value).toBeNull();
    expect(m.provenance).toMatch(/^\/api\/v1\/measurements\/[0-9a-f-]{36}\/provenance$/);
    expect(claim!.citations[0].eligibility).toBe('PENDING_VERIFICATION');
  });

  it('parses abstention and blocked comparison', () => {
    const ex = parseCopilotResponse(fixture('copilot_excluded'));
    expect(ex.status).toBe('abstained');
    expect(ex.abstention_reason).toContain('ACQUIRED_BUT_EXCLUDED');
    expect(ex.claims).toEqual([]);
    expect(parseCopilotResponse(fixture('copilot_blocked')).status).toBe('comparison_blocked');
  });

  it('rejects a value attached to an invalid measurement and unknown statuses', () => {
    const bad = structuredClone(fixture('copilot_invalid')) as { claims: { citations: { measurements: { value: number | null }[] }[] }[] };
    bad.claims[0].citations[0].measurements[0].value = 0;
    expect(() => parseCopilotResponse(bad)).toThrow();
    const unknown = { ...(fixture('copilot_clean') as object), status: 'verified' };
    expect(() => parseCopilotResponse(unknown)).toThrow();
  });

  it('calls /copilot/ask with only the question', async () => {
    mockResponse(fixture('copilot_clean'));
    await api.askCopilot('What was the initial droplet diameter in FLEX-070?');
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/copilot\/ask$/);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ question: 'What was the initial droplet diameter in FLEX-070?' });
  });
});

describe('evidence search and errors', () => {
  it('parses a real search response with flagged measurements', () => {
    const r = parseSearchResponse(fixture('search_flex114'));
    expect(r.hits.length).toBeGreaterThan(0);
    expect(r.hits.every((h) => h.chunk.source_id === 'PSI-69')).toBe(true);
    expect(r.hits[0].chunk.measurements.some((m) => m.evidence_status === 'INVALID')).toBe(true);
  });

  it('turns the real 403 for an excluded chunk into a readable message', async () => {
    mockResponse(fixture('chunk_psi25_403'), 403);
    await expect(api.searchEvidence('x')).rejects.toMatchObject({ status: 403 });
    mockResponse(fixture('chunk_psi25_403'), 403);
    const error = await api.searchEvidence('x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain('ACQUIRED_BUT_EXCLUDED');
    expect((error as ApiError).message).not.toContain('[object Object]');
  });

  it('formats FastAPI 422 details', async () => {
    mockResponse({ detail: [{ loc: ['body', 'filters', 'include_quarantined'], msg: 'Extra inputs are not permitted', type: 'extra_forbidden' }] }, 422);
    await expect(api.searchEvidence('x')).rejects.toThrow('Extra inputs are not permitted');
  });

  it('builds provenance URLs on the API base', () => {
    expect(apiUrl('/api/v1/measurements/abc/provenance')).toMatch(/^https?:\/\/[^/]+\/api\/v1\/measurements\/abc\/provenance$/);
  });
});

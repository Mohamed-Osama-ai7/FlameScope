import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../src/api/client';
import type { ComparisonRequest, SourceRecord } from '../../src/api/contracts';

afterEach(() => vi.unstubAllGlobals());

const source: SourceRecord = {
  source_id: 'PSI-69',
  source_title: 'FLEX droplet combustion',
  source_type: 'dataset',
  official_challenge_resource: false,
  source_url: 'https://example.test/flex.csv',
  doi: '10.60555/mbq8-0451',
  version_or_release: 'v1',
  retrieved_at_utc: '2026-11-13T00:00:00Z',
  license: 'NASA PSI terms',
  raw_file_path: 'data/raw/flex.csv',
  sha256: 'a'.repeat(64),
  verification_status: 'VERIFIED',
  notes: '',
};

function mockJsonResponse(payload: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status })));
}

describe('scientific API client', () => {
  it('maps a source list without dropping provenance fields', async () => {
    mockJsonResponse([source]);

    await expect(api.listSources()).resolves.toEqual([source]);
  });

  it.each([
    ['sources', () => api.listSources()],
    ['regimes', () => api.listRegimes()],
    ['methods', () => api.listMethods()],
  ])('accepts an empty %s response as an empty result', async (_resource, list) => {
    mockJsonResponse([]);

    await expect(list()).resolves.toEqual([]);
  });

  it('sends the selected descriptors and exposes the backend comparison decision', async () => {
    const request: ComparisonRequest = {
      a: { investigation_id: 'PSI-69', regime: 'flex_droplet', variable: 'K', unit: 'mm^2/s' },
      b: { investigation_id: 'PSI-69', regime: 'flex_droplet', variable: 'K', unit: 'mm^2/s' },
    };
    const result = {
      classification: 'not_comparable',
      shared_axis_allowed: false,
      reasons: ['Recorded oxygen conditions differ.'],
      held_constant: ['regime'],
      differing: ['ambient_oxygen_mole_fraction'],
      unknown: ['apparatus'],
    } as const;
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.validateComparison(request)).resolves.toEqual(result);
    expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/comparisons/validate');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual(request);
  });

  it('rejects malformed successful payloads instead of silently normalizing them', async () => {
    mockJsonResponse([{ ...source, verification_status: 'MAYBE' }]);

    await expect(api.listSources()).rejects.toThrow('Source record has an unknown verification status.');
  });

  it('preserves the backend error detail and status for failed requests', async () => {
    mockJsonResponse({ detail: 'Comparison requires two observations.' }, 422);
    const request: ComparisonRequest = {
      a: { investigation_id: 'PSI-69', regime: 'flex_droplet', variable: 'K', unit: 'mm^2/s' },
      b: { investigation_id: 'PSI-69', regime: 'flex_droplet', variable: 'K', unit: 'mm^2/s' },
    };

    await expect(api.validateComparison(request)).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Comparison requires two observations.',
      status: 422,
    });
  });

  it('rejects invalid JSON from a successful API response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{invalid', { status: 200 })));

    await expect(api.listRegimes()).rejects.toThrow('API returned invalid JSON.');
  });
});

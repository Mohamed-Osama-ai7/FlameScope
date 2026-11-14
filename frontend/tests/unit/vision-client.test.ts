import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, loadOfflineVisionBaseline } from '../../src/api/client';
import {
  parseThresholdSensitivity,
  parseVisionEvalTest,
  parseVisionEvaluation,
  parseVisionFrame,
  parseVisionFrameList,
  parseVisionTestSummary,
} from '../../src/api/visionValidation';

afterEach(() => vi.unstubAllGlobals());

function mockJsonResponse(data: unknown, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 200 ? 'OK' : 'Error',
      text: async () => JSON.stringify(data),
      json: async () => data,
    }),
  );
}

const baselinePath = resolve(__dirname, '../../public/data/flame_vision_baseline_v1.0.0.json');

describe('visionValidation on real baseline data', () => {
  const baselineRaw = JSON.parse(readFileSync(baselinePath, 'utf-8')) as {
    evaluation: unknown;
    tests: Record<string, unknown>;
    series: Record<string, unknown>;
    method: unknown;
  };

  it('validates vision evaluation response shape and benchmark values', () => {
    const parsed = parseVisionEvaluation(baselineRaw.evaluation);
    expect(parsed.method_id).toBe('vision.hibms_droplet_d2_pixel');
    expect(parsed.method_version).toBe('1.0.0');
    expect(parsed.n_tests).toBe(3);
    expect(parsed.n_computable).toBe(2);
    expect(parsed.n_abstained).toBe(1);
    expect(parsed.relative_difference_mean).toBeCloseTo(-0.185, 2);
    expect(parsed.verdict).toContain('not validated');
    expect(parsed.tests.length).toBe(3);

    // Test 20CAL10 (Methanol)
    const t10 = parsed.tests.find((t) => t.test_point === '20CAL10');
    expect(t10).toBeDefined();
    expect(t10?.computable).toBe(true);
    expect(t10?.fuel).toBe('Methanol');
    expect(t10?.fit_r_squared).toBeGreaterThan(0.99);
    expect(t10?.vision_k_over_d0sq_per_s).toBeCloseTo(0.1348, 3);
    expect(t10?.nasa_k_over_d0sq_per_s).toBeCloseTo(0.1734, 3);
    expect(t10?.relative_difference).toBeCloseTo(-0.2226, 3);

    // Test 30CAL06 (Heptane - Abstained)
    const t06 = parsed.tests.find((t) => t.test_point === '30CAL06');
    expect(t06).toBeDefined();
    expect(t06?.computable).toBe(false);
    expect(t06?.fuel).toBe('Heptane');
    expect(t06?.abstention_reason).toContain('too few measured frames');
  });

  it('validates computable test summary (20CAL10)', () => {
    const parsed = parseVisionTestSummary(baselineRaw.tests['20CAL10']);
    expect(parsed.test_point).toBe('20CAL10');
    expect(parsed.method.method_id).toBe('vision.hibms_droplet_d2_pixel');
    expect(parsed.physical_units).toBeNull();
    expect(parsed.physical_units_reason).toContain('No mm/px scale');

    // Results
    expect(parsed.results).toBeDefined();
    expect(parsed.results?.d0_px).toBeCloseTo(32.596, 2);
    expect(parsed.results?.k_px2_per_s).toBeCloseTo(143.25, 1);
    expect(parsed.results?.fit.r_squared).toBeGreaterThan(0.99);
    expect(parsed.results?.fit.n).toBe(136);

    // NASA reference
    expect(parsed.nasa_reference.run_id).toBe('PSI-69-r002');
    expect(parsed.nasa_reference.reported_k_mm2_per_s).toBe(0.6);
    expect(parsed.nasa_reference.reported_d0_mm).toBe(1.86);

    // Comparison
    expect(parsed.comparison).toBeDefined();
    expect(parsed.comparison?.relative_difference).toBeCloseTo(-0.2226, 3);
    expect(parsed.comparison?.implied_mm_per_px_from_nasa_d0).toBeCloseTo(0.0571, 3);

    // Provenance
    expect(parsed.provenance.length).toBe(4);
    expect(parsed.provenance.some((p) => p.role === 'frames_zip')).toBe(true);
  });

  it('validates abstained test summary (30CAL06)', () => {
    const parsed = parseVisionTestSummary(baselineRaw.tests['30CAL06']);
    expect(parsed.test_point).toBe('30CAL06');
    expect(parsed.computable).toBe(false);
    expect(parsed.abstention_reason).toContain('too few measured frames');
    expect(parsed.results).toBeUndefined();
    expect(parsed.nasa_reference.run_id).toBe('PSI-69-r008');
    expect(parsed.nasa_reference.fuel).toBe('Heptane');
  });

  it('validates frame time series parsing', () => {
    const frames = parseVisionFrameList(baselineRaw.series['20CAL10']);
    expect(frames.length).toBeGreaterThan(100);

    const f0 = frames[0];
    expect(f0.frame).toContain('20CAL10A_');
    expect(typeof f0.status).toBe('string');
    expect(Array.isArray(f0.flags)).toBe(true);

    const measuredFrames = frames.filter((f) => f.status === 'measured');
    expect(measuredFrames.length).toBeGreaterThan(50);
    const m0 = measuredFrames[0];
    expect(m0.diameter_px).toBeGreaterThan(0);
    expect(m0.area_px).toBeGreaterThan(0);
    expect(m0.circularity).toBeGreaterThan(0);
  });

  it('rejects malformed payloads with descriptive error', () => {
    expect(() => parseVisionEvaluation({})).toThrow(/VisionEvaluation/);
    expect(() => parseVisionEvaluation({ method_id: 123 })).toThrow(/VisionEvaluation/);
    expect(() => parseVisionTestSummary(null)).toThrow(/VisionTestSummary/);
    expect(() => parseVisionFrame('not a frame')).toThrow(/VisionFrame/);
    expect(() => parseThresholdSensitivity({ '0.4': 'bad' })).toThrow(/ThresholdSensitivity/);
  });
});

describe('api client vision methods with mock fetch', () => {
  it('calls /vision/evaluation and returns parsed result', async () => {
    const mockEval = {
      method_id: 'vision.hibms_droplet_d2_pixel',
      method_version: '1.0.0',
      tests: [],
      n_tests: 0,
      n_computable: 0,
      n_abstained: 0,
      relative_difference_mean: 0,
      relative_difference_range: [0, 0],
      implied_scale_range_mm_per_px: [0.05, 0.06],
      verdict: 'not validated',
    };
    mockJsonResponse(mockEval);

    const res = await api.getVisionEvaluation();
    expect(res.method_id).toBe('vision.hibms_droplet_d2_pixel');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/vision/evaluation'),
      expect.anything(),
    );
  });

  it('calls /vision/tests/:test_point with URL encoded parameter', async () => {
    const mockSummary = {
      test_point: '20CAL10',
      method: { method_id: 'test', version: '1', status: 'tested' },
      physical_units: null,
      physical_units_reason: 'reason',
      nasa_reference: {
        run_id: 'PSI-69-r002',
        flex_identifier: '20CAL10',
        fuel: 'Methanol',
        test_end: 'Extinction',
        reported_k_mm2_per_s: 0.6,
        reported_d0_mm: 1.86,
        reported_burn_time_s: 5.0,
        reported_k_over_d0sq_per_s: 0.173,
        value_origin: 'FLEX',
      },
      provenance: [],
      generated_at_utc: '2026-11-14T00:00:00Z',
    };
    mockJsonResponse(mockSummary);

    const res = await api.getVisionTest('20CAL10');
    expect(res.test_point).toBe('20CAL10');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/vision/tests/20CAL10'),
      expect.anything(),
    );
  });

  it('loads offline vision baseline correctly', async () => {
    const baselineData = JSON.parse(readFileSync(baselinePath, 'utf-8'));
    mockJsonResponse(baselineData);

    const baseline = await loadOfflineVisionBaseline();
    expect(baseline.evaluation.n_tests).toBe(3);
    expect(baseline.tests['20CAL10']).toBeDefined();
    expect(baseline.tests['30CAL06']).toBeDefined();
    expect(baseline.series['20CAL10'].length).toBeGreaterThan(100);
    expect(baseline.method.method_id).toBe('vision.hibms_droplet_d2_pixel');
  });
});

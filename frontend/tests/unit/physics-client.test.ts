import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, loadOfflinePhysicsBaseline } from '../../src/api/client';
import {
  parseD2Consistency,
  parseD2FuelSummary,
  parseD2RunResult,
  parseOlsModelResult,
  parseOxygenEffect,
  parseOxygenStratumResult,
  parseRegressionCoefficient,
} from '../../src/api/physicsValidation';

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

describe('physicsValidation on real baseline data', () => {
  const baselinePath = resolve(__dirname, '../../public/data/physics_baseline_v0.1.1.json');
  const baselineRaw = JSON.parse(readFileSync(baselinePath, 'utf-8')) as {
    d2_consistency: unknown;
    oxygen_effect: unknown;
  };

  it('validates d2-consistency response shape and values correctly', () => {
    const parsed = parseD2Consistency(baselineRaw.d2_consistency);
    expect(parsed.analysis).toBe('d2_consistency');
    expect(parsed.analysis_version).toBe('physics-0.1.1');
    expect(parsed.n_runs).toBe(154);
    expect(parsed.runs.length).toBe(154);

    // Heptane summary
    const heptane = parsed.by_fuel.Heptane;
    expect(heptane).toBeDefined();
    expect(heptane.n).toBe(54);
    expect(heptane.median).toBeCloseTo(0.949, 2);
    expect(heptane.median_ci95).not.toBeNull();
    expect(heptane.median_ci95![0]).toBeLessThan(heptane.median);
    expect(heptane.median_ci95![1]).toBeGreaterThan(heptane.median);
    expect(heptane.tukey_fences[0]).toBeLessThan(heptane.q1);
    expect(heptane.tukey_fences[1]).toBeGreaterThan(heptane.q3);

    // Methanol summary
    const methanol = parsed.by_fuel.Methanol;
    expect(methanol).toBeDefined();
    expect(methanol.n).toBe(100);
    expect(methanol.median).toBeCloseTo(0.951, 2);
    expect(methanol.median_ci95).not.toBeNull();

    // Flagged runs
    expect(parsed.flagged_for_review.length).toBeGreaterThan(0);
    for (const flagId of parsed.flagged_for_review) {
      const match = parsed.runs.find((r) => r.run_id === flagId);
      expect(match).toBeDefined();
      expect(match?.review_flag).toBe('outside fuel Tukey fences beyond reporting resolution');
    }

    // Limitations exist
    expect(parsed.limitations.length).toBeGreaterThanOrEqual(4);
  });

  it('validates oxygen-effect response shape, computable strata, and abstentions', () => {
    const parsed = parseOxygenEffect(baselineRaw.oxygen_effect);
    expect(parsed.analysis).toBe('oxygen_effect');
    expect(parsed.analysis_version).toBe('physics-0.1.1');
    expect(parsed.strata.length).toBe(11);

    const computable = parsed.strata.filter((s) => s.computable);
    expect(computable.length).toBe(2);

    const heptaneStratum = computable.find((s) => s.fuel === 'Heptane');
    expect(heptaneStratum).toBeDefined();
    expect(heptaneStratum?.n).toBe(22);
    expect(heptaneStratum?.model_k_on_o2).toBeDefined();
    expect(heptaneStratum?.model_k_on_o2?.x_o2.estimate).toBeGreaterThan(1.0);
    expect(heptaneStratum?.model_k_on_o2?.x_o2.se_hc3).toBeGreaterThan(0);
    expect(heptaneStratum?.model_k_on_o2?.x_o2.ci95[0]).toBeLessThan(
      heptaneStratum!.model_k_on_o2!.x_o2.estimate,
    );
    expect(heptaneStratum?.model_k_on_o2?.x_o2.ci95[1]).toBeGreaterThan(
      heptaneStratum!.model_k_on_o2!.x_o2.estimate,
    );

    const nonComputable = parsed.strata.filter((s) => !s.computable);
    expect(nonComputable.length).toBe(9);
    for (const stratum of nonComputable) {
      expect(stratum.abstention_reason).toMatch(/needs n >= 8/);
    }
  });

  it('rejects invalid payloads with strict informative errors', () => {
    expect(() => parseD2Consistency(null)).toThrow(/D2Consistency response has an invalid shape/);
    expect(() => parseD2Consistency({ analysis: 'wrong' })).toThrow(
      /D2Consistency response has an invalid shape/,
    );
    expect(() => parseD2FuelSummary({ n: 'not-a-number' })).toThrow(/D2FuelSummary/);
    expect(() => parseD2RunResult({ run_id: 123 })).toThrow(/D2RunResult/);
    expect(() => parseRegressionCoefficient({ estimate: 'invalid' })).toThrow(/RegressionCoefficient/);
    expect(() => parseOlsModelResult({})).toThrow(/OlsModelResult/);
    expect(() => parseOxygenStratumResult({ fuel: 123 })).toThrow(/OxygenStratumResult/);
    expect(() => parseOxygenEffect({ analysis: 'other' })).toThrow(
      /OxygenEffect response has an invalid shape/,
    );
  });
});

describe('api client physics methods', () => {
  it('getD2Consistency requests correct path with query params', async () => {
    const mockData = {
      analysis: 'd2_consistency',
      analysis_version: 'physics-0.1.1',
      equation: 't_d2 = (D0^2 - Dext^2) / K',
      value_origin: 'reported',
      n_runs: 1,
      excluded: {},
      by_fuel: {
        Heptane: {
          n: 1,
          median: 0.95,
          median_ci95: [0.9, 1.0],
          q1: 0.9,
          q3: 1.0,
          min: 0.9,
          max: 1.0,
          tukey_fences: [0.75, 1.15],
          share_of_intervals_containing_1: 1.0,
        },
      },
      flagged_for_review: [],
      runs: [
        {
          run_id: 'PSI-69-r001',
          experiment_id: 'FLEX-001',
          fuel: 'Heptane',
          d0_mm: 3.0,
          dext_mm: 1.0,
          k_mm2_s: 0.8,
          burn_time_s: 10.0,
          t_d2_s: 10.0,
          ratio: 1.0,
          ratio_interval: [0.95, 1.05],
          review_flag: null,
        },
      ],
      uncertainty: { per_run: 'res', summary: 'boot' },
      limitations: ['limit1', 'limit2', 'limit3', 'limit4'],
    };
    mockJsonResponse(mockData);

    const res = await api.getD2Consistency({ fuel: 'Heptane', diameter_halfwidth_mm: 0.05 });
    expect(res.analysis).toBe('d2_consistency');
    expect(res.n_runs).toBe(1);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/physics/d2-consistency?fuel=Heptane&diameter_halfwidth_mm=0.05'),
      expect.anything(),
    );
  });

  it('getOxygenEffect requests correct path with query params', async () => {
    const mockData = {
      analysis: 'oxygen_effect',
      analysis_version: 'physics-0.1.1',
      model: 'K = b0 + b1 * X_O2',
      units: { K: 'mm^2/s', X_O2: 'mole fraction' },
      value_origin: 'reported',
      strata_held_fixed: ['fuel'],
      excluded: {},
      strata: [
        {
          fuel: 'Methanol',
          pressure_cluster: '1 atm',
          support_mode: 'free_floating',
          n: 10,
          x_o2_range: [0.21, 0.4],
          n_distinct_o2: 3,
          run_ids: ['PSI-69-r001'],
          computable: false,
          abstention_reason: 'needs n >= 8 and >= 3 distinct O2 levels',
        },
      ],
      limitations: ['limit1'],
    };
    mockJsonResponse(mockData);

    const res = await api.getOxygenEffect({ fuel: 'Methanol' });
    expect(res.analysis).toBe('oxygen_effect');
    expect(res.strata.length).toBe(1);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/physics/oxygen-effect?fuel=Methanol'),
      expect.anything(),
    );
  });

  it('loadOfflinePhysicsBaseline parses the public baseline JSON', async () => {
    const baselinePath = resolve(__dirname, '../../public/data/physics_baseline_v0.1.1.json');
    const baselineData = JSON.parse(readFileSync(baselinePath, 'utf-8'));
    mockJsonResponse(baselineData);

    const loaded = await loadOfflinePhysicsBaseline();
    expect(loaded.d2_consistency.n_runs).toBe(154);
    expect(loaded.oxygen_effect.strata.length).toBe(11);
  });
});


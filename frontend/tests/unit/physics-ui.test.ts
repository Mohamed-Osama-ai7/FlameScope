import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseD2Consistency, parseOxygenEffect } from '../../src/api/physicsValidation';

describe('Physics UI data contracts and logic', () => {
  const baselinePath = resolve(__dirname, '../../public/data/physics_baseline_v0.1.1.json');
  const baseline = JSON.parse(readFileSync(baselinePath, 'utf-8')) as {
    d2_consistency: unknown;
    oxygen_effect: unknown;
  };
  const d2 = parseD2Consistency(baseline.d2_consistency);
  const o2 = parseOxygenEffect(baseline.oxygen_effect);

  describe('d2 consistency UI metrics', () => {
    it('has usable extinction runs for both Heptane and Methanol', () => {
      expect(d2.n_runs).toBe(154);
      expect(d2.by_fuel.Heptane.n).toBe(54);
      expect(d2.by_fuel.Methanol.n).toBe(100);
      expect(d2.by_fuel.Heptane.n + d2.by_fuel.Methanol.n).toBe(154);
    });

    it('reports median ratio near 0.95 reflecting FLEX linear fit convention', () => {
      // Because K is fitted from after ignition to extinction and excludes heat-up transient,
      // ratio r = t_d2 / t_burn is physically expected to be around ~0.95 rather than 1.0.
      expect(d2.by_fuel.Heptane.median).toBeCloseTo(0.949, 2);
      expect(d2.by_fuel.Methanol.median).toBeCloseTo(0.951, 2);
    });

    it('calculates deterministic 95% bootstrap confidence intervals', () => {
      const hCI = d2.by_fuel.Heptane.median_ci95;
      const mCI = d2.by_fuel.Methanol.median_ci95;
      expect(hCI).not.toBeNull();
      expect(mCI).not.toBeNull();

      expect(hCI![0]).toBeCloseTo(0.916, 2);
      expect(hCI![1]).toBeCloseTo(0.970, 2);

      expect(mCI![0]).toBeCloseTo(0.941, 2);
      expect(mCI![1]).toBeCloseTo(0.957, 2);
    });

    it('flags exactly the 9 outlier runs whose whole interval lies outside Tukey fences', () => {
      expect(d2.flagged_for_review.length).toBe(9);
      const expectedFlagged = [
        'PSI-69-r100',
        'PSI-69-r118',
        'PSI-69-r120',
        'PSI-69-r130',
        'PSI-69-r171',
        'PSI-69-r213',
        'PSI-69-r261',
        'PSI-69-r006',
        'PSI-69-r266',
      ];
      for (const flagId of expectedFlagged) {
        expect(d2.flagged_for_review).toContain(flagId);
      }
    });

    it('categorizes excluded runs with distinct scientific reasons', () => {
      const excludedKeys = Object.keys(d2.excluded);
      expect(excludedKeys.some((k) => k.includes('d^2 burn to extinction required'))).toBe(true);
      expect(excludedKeys.some((k) => k.includes('missing_or_flagged'))).toBe(true);
      expect(excludedKeys.some((k) => k.includes('row_flag:dext_exceeds_d0'))).toBe(true);
    });
  });

  describe('Oxygen effect regression UI metrics', () => {
    it('holds diluent (N2 only), pressure cluster, and support mode fixed', () => {
      expect(o2.strata_held_fixed).toEqual([
        'fuel',
        'diluent_family = N2_only',
        'pressure_cluster',
        'support_mode',
      ]);
    });

    it('isolates exactly 2 computable strata with n >= 8 and >= 3 O2 levels', () => {
      const computable = o2.strata.filter((s) => s.computable);
      expect(computable).toHaveLength(2);

      const fuels = computable.map((s) => s.fuel).sort();
      expect(fuels).toEqual(['Heptane', 'Methanol']);

      for (const s of computable) {
        expect(s.n).toBeGreaterThanOrEqual(8);
        expect(s.n_distinct_o2).toBeGreaterThanOrEqual(3);
        expect(s.model_k_on_o2).toBeDefined();
        // Positive slope
        expect(s.model_k_on_o2!.x_o2.estimate).toBeGreaterThan(0);
        // Robust SE
        expect(s.model_k_on_o2!.x_o2.se_hc3).toBeGreaterThan(0);
        // Statistically significant
        expect(s.model_k_on_o2!.x_o2.p_value).toBeLessThan(0.01);
      }
    });

    it('demonstrates slope stability in D0-adjusted sensitivity check', () => {
      const computable = o2.strata.filter((s) => s.computable);
      for (const s of computable) {
        expect(s.sensitivity_k_on_o2_and_d0).toBeDefined();
        const primarySlope = s.model_k_on_o2!.x_o2.estimate;
        const adjustedSlope = s.sensitivity_k_on_o2_and_d0!.x_o2.estimate;
        // Controlling for D0 leaves slope positive and within ~10% of primary estimate
        expect(adjustedSlope).toBeGreaterThan(0);
        expect(Math.abs(primarySlope - adjustedSlope)).toBeLessThan(0.5);
      }
    });

    it('explicitly abstains on all 9 underpowered strata with scientific reason', () => {
      const abstained = o2.strata.filter((s) => !s.computable);
      expect(abstained).toHaveLength(9);
      for (const s of abstained) {
        expect(s.abstention_reason).toBe('needs n >= 8 and >= 3 distinct O2 levels');
        expect(s.model_k_on_o2).toBeUndefined();
      }
    });

    it('prominently includes all 4 scientific limitations in both responses', () => {
      expect(d2.limitations).toHaveLength(4);
      expect(d2.limitations[0]).toMatch(/Diagnostic of internal consistency/);

      expect(o2.limitations).toHaveLength(4);
      expect(o2.limitations[0]).toMatch(/Association within strata, not a causal effect/);
    });
  });
});

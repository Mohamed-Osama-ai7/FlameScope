import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { parseCopilotResponse } from '../../src/api/ragValidation';
import { clampG, flameGeometry } from '../../src/quasar/buoyancy';

const fixture = (name: string): Record<string, unknown> =>
  JSON.parse(readFileSync(new URL(`../fixtures/api/${name}.json`, import.meta.url), 'utf8')) as Record<string, unknown>;

describe('flame geometry (schematic buoyancy model)', () => {
  it('is a sphere with diffusion only at 0 g', () => {
    const g0 = flameGeometry(0);
    expect(g0.height).toBeCloseTo(2 * 58, 5);
    expect(g0.width).toBeCloseTo(2 * 58, 5);
    expect(g0.convection).toBe(0);
    expect(g0.diffusion).toBe(1);
    expect(g0.core).toBe('#4fa8ff');
  });

  it('is a tall pinched teardrop with convection at 1 g', () => {
    const g1 = flameGeometry(1);
    expect(g1.height).toBeGreaterThan(flameGeometry(0).height * 1.5);
    expect(g1.width).toBeLessThan(flameGeometry(0).width);
    expect(g1.convection).toBe(1);
    expect(g1.diffusion).toBe(0);
    expect(g1.core).toBe('#ffb347');
  });

  it('changes monotonically and always yields a closed path', () => {
    let prevHeight = -1;
    for (let i = 0; i <= 10; i++) {
      const geo = flameGeometry(i / 10);
      expect(geo.height).toBeGreaterThan(prevHeight);
      prevHeight = geo.height;
      expect(geo.path.startsWith('M ') && geo.path.endsWith('Z')).toBe(true);
      expect(geo.path).not.toMatch(/NaN|undefined/);
    }
  });

  it('clamps out-of-range and non-finite gravity', () => {
    expect(clampG(5)).toBe(1);
    expect(clampG(-2)).toBe(0);
    expect(clampG(Number.NaN)).toBe(0);
    expect(flameGeometry(Number.NaN).convection).toBe(0);
  });
});

describe('Copilot uncertainty items (real API response)', () => {
  it('parses the live FLEX-114 answer with its uncertainty items', () => {
    const r = parseCopilotResponse(fixture('copilot_flex114_uncertainty'));
    const keys = (r.uncertainty ?? []).map((u) => `${u.kind}:${u.code}`);
    expect(keys).toContain('measurement:invalid_value');
    expect(keys).toContain('data:source_pending_verification');
    expect(Object.keys(r)).not.toContain('confidence');
  });

  it('still parses an older response without the field', () => {
    const { uncertainty: _omit, ...older } = fixture('copilot_flex114_uncertainty');
    expect(parseCopilotResponse(older).uncertainty).toBeUndefined();
  });

  it('rejects malformed uncertainty items', () => {
    const bad = { ...fixture('copilot_flex114_uncertainty'), uncertainty: [{ kind: 'vibes', code: 'x', detail: 'y', evidence: [] }] };
    expect(() => parseCopilotResponse(bad)).toThrow();
    expect(() => parseCopilotResponse({ ...fixture('copilot_flex114_uncertainty'), uncertainty: 'none' })).toThrow();
  });
});

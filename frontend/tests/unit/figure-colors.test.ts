/**
 * Plotly 4 replaced its colour parser (TinyColor -> culori). Every colour handed to Plotly must stay in a format
 * both parsers accept: 6-digit hex or comma-separated rgba() with a 0..1 alpha. This scans every colour attribute of
 * every figure the lab can produce, and the CSS tokens that LabContext reads at runtime.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { coverageHeatmap, distributionFigure, scatterFigure, SERIES, type ChartTheme } from '../../src/lab/charts/specs';
import { validateDataset } from '../../src/lab/data/load';
import { defaultFilters, viewData, VIEWS } from '../../src/lab/data/selectors';
import type { LabDataset } from '../../src/lab/data/types';

const HEX = /^#[0-9a-fA-F]{6}$/;
const RGBA = /^rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*(?:0|1|0?\.\d+)\s*\)$/;
const ok = (c: string) => HEX.test(c) || RGBA.test(c);

const d = validateDataset(JSON.parse(readFileSync('public/data/flex_lab_dataset_v0.2.0.json', 'utf-8')) as LabDataset);
const all = { ...defaultFilters(d.records), supportModes: ['free_floating', 'fiber_translated', 'fiber_translation_not_stated', 'conflicting_sources'] as never };

const css = readFileSync('src/style.css', 'utf-8');
function tokens(block: RegExp) {
  const body = block.exec(css)?.[1] ?? '';
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}
const dark = tokens(/:root\s*\{([\s\S]*?)\n\}/);
const light = tokens(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\n\}/);
const TOKENS_USED_BY_PLOTLY = ['--surface-1', '--text-1', '--text-2', '--grid', '--axis'];

function themeOf(mode: 'light' | 'dark'): ChartTheme {
  const t = mode === 'dark' ? dark : light;
  return { mode, bg: t['--surface-1'], fg: t['--text-1'], muted: t['--text-2'], grid: t['--grid'], axis: t['--axis'], series: SERIES[mode], font: 'Inter' };
}

function collectColors(node: unknown, path: string, out: { path: string; value: string }[]) {
  if (Array.isArray(node)) {
    node.forEach((x, i) => collectColors(x, `${path}[${i}]`, out));
  } else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      if (/colorscale$/i.test(k) && Array.isArray(v)) {
        for (const stop of v as [number, string][]) out.push({ path: `${path}.${k}`, value: stop[1] });
      } else if (/color$/i.test(k) && typeof v === 'string') {
        out.push({ path: `${path}.${k}`, value: v });
      } else if (/color$/i.test(k) && Array.isArray(v)) {
        (v as unknown[]).forEach((c) => typeof c === 'string' && out.push({ path: `${path}.${k}`, value: c }));
      } else {
        collectColors(v, `${path}.${k}`, out);
      }
    }
  }
}

describe('Plotly colour compatibility (v3 and v4 parsers)', () => {
  it('CSS tokens read by the charts are 6-digit hex in both themes', () => {
    for (const [name, t] of [['dark', dark], ['light', light]] as const) {
      for (const tok of TOKENS_USED_BY_PLOTLY) expect(ok(t[tok]), `${name} ${tok} = ${t[tok]}`).toBe(true);
    }
  });
  it('the palette constants are hex', () => {
    for (const mode of ['light', 'dark'] as const) for (const c of SERIES[mode]) expect(HEX.test(c)).toBe(true);
  });
  for (const mode of ['light', 'dark'] as const) {
    it(`every colour in every figure is parser-safe (${mode} theme)`, () => {
      const t = themeOf(mode);
      const figures = [
        ...(['k_o2', 'k_pressure', 'k_co2', 'k_he', 'k_d0', 'dext_o2', 'cond_p_o2', 'outcome_o2_d0'] as const).map((id) => scatterFigure(d, viewData(d.records, VIEWS[id], all), t, d.records[0].record_key)),
        distributionFigure(d, viewData(d.records, VIEWS.k_dist, all), t, 'box', d.records[0].record_key),
        distributionFigure(d, viewData(d.records, VIEWS.k_dist, all), t, 'ecdf', null),
        coverageHeatmap(d.records, t, 'Methanol'),
      ];
      const found: { path: string; value: string }[] = [];
      figures.forEach((f, i) => { collectColors(f.data, `fig${i}.data`, found); collectColors(f.layout, `fig${i}.layout`, found); });
      expect(found.length).toBeGreaterThan(50);
      const bad = found.filter((c) => !ok(c.value));
      expect(bad, `unsupported colour strings: ${JSON.stringify(bad.slice(0, 5))}`).toEqual([]);
    });
  }
});

/** Unit tests on the ACTUAL verified v0.2.0 FLEX dataset (no synthetic records). */
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { analysisSummary, chartConfig, CSV_COLUMNS, recordsToCsv } from '../../src/lab/data/export';
import { validateDataset } from '../../src/lab/data/load';
import {
  applyFilters, defaultFilters, ecdf, qualityWarnings, strataFor, viewData, VIEWS, type Filters,
} from '../../src/lab/data/selectors';
import { distributionFigure, scatterFigure, SERIES, type ChartTheme } from '../../src/lab/charts/specs';
import type { LabDataset } from '../../src/lab/data/types';

const PATH = 'public/data/flex_lab_dataset_v0.2.0.json';
const bytes = readFileSync(PATH);
const d = validateDataset(JSON.parse(bytes.toString('utf-8')) as LabDataset);
const theme: ChartTheme = { mode: 'light', bg: '#fff', fg: '#000', muted: '#555', grid: '#eee', axis: '#999', series: SERIES.light, font: 'Inter' };
const all = (): Filters => ({ ...defaultFilters(d.records), supportModes: ['free_floating', 'fiber_translated', 'fiber_translation_not_stated', 'conflicting_sources'] });

describe('dataset contract and identity', () => {
  it('has the verified scope and provenance', () => {
    expect(d.synthetic).toBe(false);
    expect(d.analysis_version).toBe('0.2.0');
    expect(d.records).toHaveLength(274);
    expect(d.scope.unique_flex_tests).toBe(274);
    expect(d.scope.unique_identifiers).toBe(273);
    expect(d.provenance.raw_sha256).toBe('37c88ce8ae9391b7544ff630a45ce87543d04d317cdbfbed104fe7d5c27e1b96');
    expect(d.provenance.enrichment_sha256).toMatch(/^[0-9a-f]{64}$/);
  });
  it('keeps duplicate identifiers as distinct records with stable keys', () => {
    const dup = d.records.filter((r) => r.identifier === '193F001');
    expect(dup.map((r) => r.flex_test_number).sort()).toEqual([70, 73]);
    expect(new Set(dup.map((r) => r.record_key)).size).toBe(2);
    expect(new Set(d.records.map((r) => r.record_key)).size).toBe(274);
  });
  it('carries units with mm²/s for reported K', () => {
    expect(d.units.burning_rate_constant_mm2_s).toBe('mm²/s');
    expect(d.raw_headers.burning_rate_constant_mm2_s).toBe('Burning rate; mm');
  });
});

describe('filters and eligibility', () => {
  it('default filters show free-floating only and account for every record', () => {
    const f = defaultFilters(d.records);
    expect(f.supportModes).toEqual(['free_floating']);
    const { included, excludedByFilter } = applyFilters(d.records, f);
    expect(included.length + Object.values(excludedByFilter).reduce((a, b) => a + b, 0)).toBe(274);
    expect(included.every((r) => r.support_mode === 'free_floating')).toBe(true);
    expect(included.length).toBe(209);
  });
  it('K vs O2 uses only A1-eligible N2-only records and never pools fuels or support modes', () => {
    const vd = viewData(d.records, VIEWS.k_o2, all());
    expect(vd.eligible.every((r) => r.eligible.includes('A1') && r.diluent_family === 'N2_only')).toBe(true);
    expect(vd.eligible.length).toBe(d.records.filter((r) => r.eligible.includes('A1')).length);
    for (const p of vd.panels) expect(p.records.every((r) => r.fuel === p.fuel && r.support_mode === p.support)).toBe(true);
    expect(vd.panels.reduce((a, p) => a + p.records.length, 0)).toBe(vd.shown.length);
    expect(vd.eligible.length + Object.values(vd.ineligible).reduce((a, b) => a + b, 0)).toBe(274);
  });
  it('A6 extinction view contains only diameters without noted extrapolation', () => {
    const vd = viewData(d.records, VIEWS.dext_o2, all());
    expect(vd.eligible.length).toBeGreaterThan(0);
    expect(vd.eligible.every((r) => r.dext_origin === 'reported_extinction_no_extrapolation_noted')).toBe(true);
  });
  it('A6 exclusion reasons keep NASA extinction-diameter semantics distinct (never a merged "missing")', () => {
    const vd = viewData(d.records, VIEWS.dext_o2, all());
    const keys = Object.keys(vd.ineligible);
    expect(keys.some((k) => k.includes("No finite-size extinction"))).toBe(true);
    expect(keys.some((k) => k.includes('Not listed: insufficient HiBMs'))).toBe(true);
    expect(keys.some((k) => k.includes("Conflicting: '–' with test end Extinction"))).toBe(true);
    expect(keys.some((k) => k.includes('missing_dash_marker') || k.includes('missing_blank'))).toBe(false);
  });
  it('FLEX-114 invalid pressure never appears in pressure-based views', () => {
    for (const v of [VIEWS.k_pressure, VIEWS.cond_p_o2, VIEWS.k_o2]) {
      expect(viewData(d.records, v, all()).shown.some((r) => r.flex_test_number === 114)).toBe(false);
    }
  });
  it('FLEX-130 (K = 0.05) is retained as reported and only shown in fiber-translated panels', () => {
    const r = d.records.find((x) => x.flex_test_number === 130)!;
    expect(r.values.burning_rate_constant_mm2_s).toBe(0.05);
    const vd = viewData(d.records, VIEWS.k_dist, all());
    const panel = vd.panels.find((p) => p.records.includes(r))!;
    expect(panel.support).toBe('fiber_translated');
  });
  it('hiding sensitivity rows is a visual filter with an explicit reason', () => {
    const f = { ...all(), hideSensitivityRows: true };
    const { excludedByFilter } = applyFilters(d.records, f);
    expect(excludedByFilter['sensitivity rows hidden']).toBe(10);
  });
});

describe('figures', () => {
  it('scatter points map 1:1 to shown record keys, with units in axis titles', () => {
    const vd = viewData(d.records, VIEWS.k_o2, all());
    const fig = scatterFigure(d, vd, theme, null);
    const keys = fig.data.flatMap((t) => (t as { customdata?: string[] }).customdata ?? []);
    expect(keys.length).toBe(vd.shown.length);
    expect(new Set(keys)).toEqual(new Set(vd.shown.map((r) => r.record_key)));
    expect(JSON.stringify(fig.layout.yaxis)).toContain('mm²/s');
  });
  it('a selected record is drawn as an extra ring trace in its panel only', () => {
    const vd = viewData(d.records, VIEWS.k_o2, all());
    const key = vd.shown[0].record_key;
    const fig = scatterFigure(d, vd, theme, key);
    const rings = fig.data.filter((t) => (t as { name?: string }).name === 'Selected record');
    expect(rings).toHaveLength(1);
    expect((rings[0] as { customdata: string[] }).customdata).toEqual([key]);
  });
  it('empty panels are labelled instead of silently disappearing', () => {
    const f = { ...all(), testEnds: ['Completion'] };
    const vd = viewData(d.records, VIEWS.dext_o2, f);
    const fig = scatterFigure(d, vd, theme, null);
    expect(JSON.stringify(fig.layout.annotations)).toContain('No eligible records');
  });
  it('distribution keeps every observation', () => {
    const vd = viewData(d.records, VIEWS.k_dist, all());
    const fig = distributionFigure(d, vd, theme, 'box', null);
    const n = fig.data.reduce((a, t) => a + ((t as { y: number[] }).y?.length ?? 0), 0);
    expect(n).toBe(vd.shown.length);
  });
  it('ECDF is a step function ending at 1', () => {
    const e = ecdf([3, 1, 2, 2]);
    expect(e.x).toEqual([1, 2, 2, 3]);
    expect(e.y).toEqual([0.25, 0.5, 0.75, 1]);
  });
});

describe('statistics come from Python, not the browser', () => {
  it('strata rho values are passed through unchanged from the v0.2.0 summary', () => {
    const summary = JSON.parse(readFileSync('../reports/flex_run_level_v0.2/summary.json', 'utf-8'));
    const py = summary.results.strata.filter((s: { rho_spearman: number | null }) => s.rho_spearman !== null);
    const ours = d.strata.filter((s) => s.rho_spearman !== null);
    expect(ours.map((s) => s.rho_spearman)).toEqual(py.map((s: { rho_spearman: number }) => s.rho_spearman));
    expect(strataFor(d, 'A1', ['free_floating'], ['Methanol', 'Heptane']).every((s) => s.stratum.support_mode === 'free_floating')).toBe(true);
  });
  it('dataset records the SHA-256 of the v0.2.0 summary it was built from', () => {
    const h = createHash('sha256').update(readFileSync('../reports/flex_run_level_v0.2/summary.json')).digest('hex');
    expect(d.provenance.analysis_summary_sha256).toBe(h);
  });
});

describe('quality warnings', () => {
  const w = qualityWarnings(d);
  it('link duplicates, invalid pressure and source-level gaps to records or rules', () => {
    expect(w.find((x) => x.rule === 'quality.duplicate_source_identifier')!.recordKeys).toHaveLength(2);
    const p = w.find((x) => x.rule === 'quality.invalid_nonpositive_pressure')!;
    expect(p.recordKeys).toHaveLength(1);
    expect(p.recordKeys[0]).toContain('FLEX-114');
    expect(w.find((x) => x.rule === 'evidence.unmapped_tests')!.recordKeys).toHaveLength(0);
    expect(w.every((x) => x.rule in d.rules)).toBe(true);
    expect(JSON.stringify(w)).not.toMatch(/score/i);
  });
});

describe('exports', () => {
  it('CSV keeps record IDs, raw values, units, provenance and the export type', () => {
    const csv = recordsToCsv(d, d.records);
    const lines = csv.trim().split('\n');
    expect(lines[0]).toBe(CSV_COLUMNS.join(','));
    expect(lines).toHaveLength(275);
    expect(csv).toContain('PSI69-r130|FLEX-130|C13H201|9/17/2010|3:55:59');
    expect(csv).toContain(d.provenance.raw_sha256);
    expect(csv).toContain('filtered raw observations (NASA-reported values; no calculation)');
    expect(csv).toContain('mm²/s');
    expect(csv).toContain('Extinction'); // NASA outcome semantics preserved verbatim
  });
  it('chart config and analysis summary carry filters, record keys and provenance', () => {
    const f = all();
    const vd = viewData(d.records, VIEWS.k_o2, f);
    const cfg = chartConfig(d, vd, f);
    expect(cfg.provenance.raw_sha256).toBe(d.provenance.raw_sha256);
    expect(cfg.panels.flatMap((p) => p.record_keys).sort()).toEqual(vd.shown.map((r) => r.record_key).sort());
    expect(cfg.view.units.y).toBe('mm²/s');
    const s = analysisSummary(d, f);
    expect(s.strata).toHaveLength(d.strata.length);
    expect(s.export_type).toContain('aggregated');
  });
  it('the shipped dataset file is the one generated by the Python exporter (hash recorded in docs)', () => {
    expect(createHash('sha256').update(bytes).digest('hex')).toMatch(/^[0-9a-f]{64}$/);
  });
});

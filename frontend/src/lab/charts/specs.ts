/**
 * Pure Plotly figure builders (no React). Each panel = one fuel × one support mode; panels are never pooled.
 * Every plotted point carries its record_key in customdata so selection maps to the exact source record.
 */
import type { Data, Layout, Shape } from 'plotly.js';
import type { ViewData } from '../data/selectors';
import { DEXT_CLASS, ecdf, groupOf, PRESSURE_TIERS } from '../data/selectors';
import type { FlexRecord, LabDataset, NumericField } from '../data/types';
import { FAMILY_LABEL, FIELD_LABEL, SUPPORT_LABEL } from '../data/types';

export interface ChartTheme {
  mode: 'light' | 'dark';
  bg: string;
  fg: string;
  muted: string;
  grid: string;
  axis: string;
  series: [string, string, string];
  font: string;
}

/** Validated categorical slots 1-3 (dataviz reference palette; all-pairs CVD-safe for scatter). */
export const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a'] as [string, string, string],
  dark: ['#3987e5', '#d95926', '#199e70'] as [string, string, string],
};
export const SYMBOLS = ['circle', 'square', 'triangle-up'] as const;

export interface Figure {
  data: Data[];
  layout: Partial<Layout>;
  groups: string[];
}

const GROUP_ORDER: Record<string, string[]> = {
  pressure_tier: PRESSURE_TIERS,
  family: ['N2_only', 'CO2_added', 'He_added'],
  test_end: ['Extinction', 'Disruption', 'Completion'],
  dext_class: ['Eligible (A6)', 'Extrapolated (not in A6)'],
};

export function groupLabel(colorBy: string, g: string): string {
  if (colorBy === 'family') return FAMILY_LABEL[g as keyof typeof FAMILY_LABEL] ?? g;
  return g;
}

export function axisTitle(d: LabDataset, f: NumericField): string {
  return `${FIELD_LABEL[f]} (${d.units[f]})`;
}

function hover(d: LabDataset, r: FlexRecord): string {
  const v = r.values;
  return [
    `<b>FLEX-${String(r.flex_test_number).padStart(3, '0')}</b> · ${r.identifier} · PSI row ${r.psi_row}`,
    `${r.fuel} · ${SUPPORT_LABEL[r.support_mode]} · ${r.test_end}`,
    `K ${v.burning_rate_constant_mm2_s ?? 'missing'} ${d.units.burning_rate_constant_mm2_s} · D₀ ${v.initial_droplet_diameter ?? 'missing'} mm`,
    `P ${v.ambient_pressure} mmHg · O₂ ${v.ambient_oxygen_mole_fraction} · CO₂ ${v.co2_mole_fraction} · He ${v.ambient_helium_mole_fraction}`,
    'Click to open the evidence inspector',
  ].join('<br>');
}

function baseLayout(t: ChartTheme, rows: number, cols: number): Partial<Layout> {
  return {
    paper_bgcolor: t.bg,
    plot_bgcolor: t.bg,
    font: { family: t.font, color: t.fg, size: 12 },
    margin: { l: 64, r: 16, t: 78, b: 56 },
    grid: { rows, columns: cols, pattern: 'independent', xgap: 0.08, ygap: 0.22 },
    legend: { orientation: 'h', yref: 'container', y: 1, yanchor: 'top', x: 0, font: { color: t.muted } },
    hoverlabel: { bgcolor: t.bg, bordercolor: t.axis, font: { color: t.fg } },
    showlegend: true,
    dragmode: false,
  };
}

function axisStyle(t: ChartTheme, title: string) {
  return { title: { text: title, font: { size: 12 } }, gridcolor: t.grid, linecolor: t.axis, zeroline: false,
    tickfont: { color: t.muted }, automargin: true };
}

/** Scatter small multiples for a view; selectedKey is drawn as a ring in every panel containing it. */
export function scatterFigure(d: LabDataset, vd: ViewData, t: ChartTheme, selectedKey: string | null, narrow = false): Figure {
  const v = vd.view;
  if (!v.x) throw new Error('scatterFigure requires an x variable');
  const cols = narrow ? 1 : Math.max(1, new Set(vd.panels.map((p) => p.fuel)).size);
  const rows = Math.max(1, Math.ceil(vd.panels.length / cols));
  const layout = baseLayout(t, rows, cols);
  const data: Data[] = [];
  const order = GROUP_ORDER[v.colorBy];
  const present = new Set<string>();
  const annotations: NonNullable<Layout['annotations']> = [];

  vd.panels.forEach((p, i) => {
    const ax = i === 0 ? '' : String(i + 1);
    (layout as Record<string, unknown>)[`xaxis${ax}`] = { ...axisStyle(t, axisTitle(d, v.x as NumericField)), matches: 'x' };
    (layout as Record<string, unknown>)[`yaxis${ax}`] = { ...axisStyle(t, axisTitle(d, v.y)), matches: 'y' };
    annotations.push({
      text: `<b>${p.fuel}</b> · ${SUPPORT_LABEL[p.support]} · n = ${p.records.length}`,
      xref: `x${ax} domain` as never, yref: `y${ax} domain` as never, x: 0, y: 1.02, xanchor: 'left', yanchor: 'bottom',
      showarrow: false, font: { size: 12, color: t.fg },
    });
    if (p.records.length === 0) {
      annotations.push({ text: 'No eligible records for this panel', xref: `x${ax} domain` as never,
        yref: `y${ax} domain` as never, x: 0.5, y: 0.5, showarrow: false, font: { color: t.muted } });
    }
    order.forEach((g, gi) => {
      const recs = p.records.filter((r) => groupOf(r, v.colorBy) === g);
      if (!recs.length) return;
      const first = !present.has(g);
      present.add(g);
      data.push({
        type: 'scatter', mode: 'markers', name: groupLabel(v.colorBy, g), legendgroup: g, showlegend: first,
        x: recs.map((r) => r.values[v.x as NumericField]), y: recs.map((r) => r.values[v.y]),
        customdata: recs.map((r) => r.record_key) as never,
        text: recs.map((r) => hover(d, r)), hovertemplate: '%{text}<extra></extra>',
        xaxis: `x${ax}`, yaxis: `y${ax}`,
        marker: {
          color: v.colorBy === 'dext_class' && gi === 1 ? t.bg : t.series[gi % 3],
          symbol: SYMBOLS[gi % 3], size: 9,
          line: { color: v.colorBy === 'dext_class' && gi === 1 ? t.series[1] : t.bg, width: 2 },
        },
      } as Data);
    });
    const sel = p.records.find((r) => r.record_key === selectedKey);
    if (sel) {
      data.push({
        type: 'scatter', mode: 'markers', name: 'Selected record', legendgroup: 'selected', showlegend: false,
        x: [sel.values[v.x as NumericField]], y: [sel.values[v.y]], customdata: [sel.record_key] as never,
        text: [hover(d, sel)], hovertemplate: '%{text}<extra>selected</extra>', xaxis: `x${ax}`, yaxis: `y${ax}`,
        marker: { size: 20, color: 'rgba(0,0,0,0)', line: { color: t.fg, width: 3 }, symbol: 'circle' },
      } as Data);
    }
  });
  layout.annotations = annotations;
  layout.height = 150 + rows * 300;
  return { data, layout, groups: order.filter((g) => present.has(g)) };
}

/** Distribution of the view's y variable: box with every observation visible, or ECDF; one group per fuel × support. */
export function distributionFigure(d: LabDataset, vd: ViewData, t: ChartTheme, mode: 'box' | 'ecdf', selectedKey: string | null): Figure {
  const layout = baseLayout(t, 1, 1);
  delete layout.grid;
  const data: Data[] = [];
  const yf = vd.view.y;
  const yTitle = axisTitle(d, yf);
  const groups = vd.panels.filter((p) => p.records.length > 0);
  groups.forEach((p, i) => {
    const name = `${p.fuel} · ${SUPPORT_LABEL[p.support]} (n = ${p.records.length})`;
    const ys = p.records.map((r) => r.values[yf] as number);
    const color = t.series[(p.fuel === 'Methanol' ? 0 : 1) % 3];
    if (mode === 'box') {
      data.push({
        type: 'box', name, y: ys, boxpoints: 'all', jitter: 0.45, pointpos: 0,
        customdata: p.records.map((r) => r.record_key) as never, text: p.records.map((r) => hover(d, r)),
        hovertemplate: '%{text}<extra></extra>', marker: { color, size: 7, symbol: SYMBOLS[i % 3], line: { color: t.bg, width: 1 } },
        line: { color: t.muted, width: 1 }, fillcolor: 'rgba(0,0,0,0)',
      } as Data);
    } else {
      const sorted = [...p.records].sort((a, b) => (a.values[yf] as number) - (b.values[yf] as number));
      const e = ecdf(ys);
      data.push({
        type: 'scatter', mode: 'lines+markers', name, x: e.x, y: e.y, line: { shape: 'hv', color, width: 2 },
        marker: { color, symbol: SYMBOLS[i % 3], size: 6 }, customdata: sorted.map((r) => r.record_key) as never,
        text: sorted.map((r) => hover(d, r)), hovertemplate: '%{text}<br>ECDF %{y:.2f}<extra></extra>',
      } as Data);
    }
  });
  const sel = vd.shown.find((r) => r.record_key === selectedKey);
  const shapes: Partial<Shape>[] = [];
  if (sel && sel.values[yf] !== null) {
    const k = sel.values[yf] as number;
    shapes.push(mode === 'box'
      ? { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: k, y1: k, line: { color: t.fg, dash: 'dot', width: 1.5 } }
      : { type: 'line', yref: 'paper', y0: 0, y1: 1, x0: k, x1: k, line: { color: t.fg, dash: 'dot', width: 1.5 } });
  }
  layout.shapes = shapes;
  layout.xaxis = mode === 'box' ? { ...axisStyle(t, 'Fuel · support mode'), type: 'category' } : axisStyle(t, yTitle);
  layout.yaxis = mode === 'box' ? axisStyle(t, yTitle) : { ...axisStyle(t, 'Empirical cumulative fraction'), range: [0, 1.02] };
  layout.height = 460;
  layout.showlegend = mode === 'ecdf';
  return { data, layout, groups: groups.map((p) => `${p.fuel}|${p.support}`) };
}

/** Count heatmap (diluent family × pressure cluster) with every count printed; counts only. */
export function coverageHeatmap(records: FlexRecord[], t: ChartTheme, fuel: string): Figure {
  const fams = ['N2_only', 'CO2_added', 'He_added'];
  const clusters = [...new Set(records.map((r) => r.pressure_cluster ?? 'pressure invalid'))].sort();
  const z = fams.map((f) => clusters.map((c) => records.filter((r) => r.fuel === fuel && r.diluent_family === f && (r.pressure_cluster ?? 'pressure invalid') === c).length));
  const ramp = t.mode === 'light' ? [[0, '#f3f6fb'], [1, '#1d5fb3']] : [[0, '#16202c'], [1, '#5aa0f0']];
  return {
    data: [{
      type: 'heatmap', z, x: clusters.map((c) => c.replace(' nominal', '')), y: fams.map((f) => FAMILY_LABEL[f as keyof typeof FAMILY_LABEL]),
      colorscale: ramp as never, showscale: false, texttemplate: '%{z}', hovertemplate: '%{y} · %{x}: %{z} records<extra></extra>',
      xgap: 3, ygap: 3, textfont: { color: t.fg },
    } as Data],
    layout: { ...baseLayout(t, 1, 1), grid: undefined, height: 260, margin: { l: 90, r: 10, t: 30, b: 90 },
      title: { text: `${fuel}: records per diluent family × pressure cluster`, font: { size: 13 } },
      xaxis: { tickfont: { color: t.muted }, tickangle: -20 }, yaxis: { tickfont: { color: t.muted } } },
    groups: [],
  };
}

export function dextClassLabel(origin: string): string {
  return DEXT_CLASS[origin] ?? origin;
}

/**
 * SYNTHETIC rendering benchmark harness (dev tool; never part of the application bundle).
 * Renders through the SAME code path as the lab: viewData -> scatterFigure -> <Plot> (react-plotly.js + the
 * lazily-loaded cartesian Plotly engine). Timing is measured in-page with performance.now().
 */
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { Plot } from '../src/lab/components/Plot';
import { scatterFigure, SERIES, type ChartTheme } from '../src/lab/charts/specs';
import { defaultFilters, viewData, VIEWS, type Filters } from '../src/lab/data/selectors';
import type { FlexRecord, LabDataset } from '../src/lab/data/types';
import { loadPlotly } from '../src/lab/plotly';
import { syntheticDataset, syntheticRecords } from './synthetic';

type Renderer = 'scatter'; // the cartesian-only engine has no scattergl (WebGL) trace
const theme: ChartTheme = {
  mode: 'light', bg: '#ffffff', fg: '#0b1220', muted: '#4a5566', grid: '#e6e9ee', axis: '#8a93a0',
  series: SERIES.light, font: 'Inter, "Segoe UI", sans-serif',
};

const st: {
  records: FlexRecord[]; dataset: LabDataset | null; root: Root | null; host: HTMLElement | null; gd: HTMLElement | null;
  renderer: Renderer; flip: { filter: boolean; select: boolean };
} = { records: [], dataset: null, root: null, host: null, gd: null, renderer: 'scatter', flip: { filter: false, select: false } };

let pending: ((t: number) => void) | null = null;
function onReady(el: HTMLElement) {
  st.gd = el;
  const p = pending;
  if (p) {
    pending = null;
    p(performance.now());
  }
}
function waitReady(ms = 300_000) {
  return new Promise<number>((resolve, reject) => {
    pending = resolve;
    setTimeout(() => {
      if (pending === resolve) {
        pending = null;
        reject(new Error('Plot did not report ready'));
      }
    }, ms);
  });
}
const afterPaint = () => new Promise<number>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(performance.now()))));

function heapBytes(): number | null {
  const m = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
  return m ? m.usedJSHeapSize : null;
}
function gc() {
  (window as unknown as { gc?: () => void }).gc?.();
}

function build(filters: Filters, selectedKey: string | null) {
  const vd = viewData(st.records, VIEWS.k_o2, filters);
  const fig = scatterFigure(st.dataset as LabDataset, vd, theme, selectedKey);
  return { fig, points: vd.shown.length };
}

async function render(filters: Filters, selectedKey: string | null) {
  const t0 = performance.now();
  const { fig, points } = build(filters, selectedKey);
  const t1 = performance.now();
  const ready = waitReady();
  flushSync(() => st.root?.render(<Plot data={fig.data} layout={fig.layout} label="synthetic benchmark chart" onReady={onReady} />));
  const tReady = await ready;
  const tPaint = await afterPaint();
  return { specMs: t1 - t0, plotMs: tReady - t1, paintMs: tPaint - t1, points };
}

const all = (): Filters => defaultFilters(st.records);
const subset = (): Filters => ({ ...defaultFilters(st.records), fuels: ['Methanol'] });

const api = {
  prepare(n: number, renderer: Renderer) {
    st.records = syntheticRecords(n);
    st.dataset = syntheticDataset(st.records);
    st.renderer = renderer;
    st.flip = { filter: false, select: false };
    return { n: st.records.length, synthetic: st.dataset.synthetic };
  },
  async mount() {
    api.unmount();
    st.host = document.createElement('div');
    document.getElementById('root')?.appendChild(st.host);
    st.root = createRoot(st.host);
    return render(all(), null);
  },
  async filterUpdate() {
    st.flip.filter = !st.flip.filter;
    return render(st.flip.filter ? subset() : all(), null);
  },
  async selectUpdate() {
    st.flip.select = !st.flip.select;
    return render(all(), st.flip.select ? st.records[Math.floor(st.records.length / 3)].record_key : null);
  },
  async exportImage(format: 'svg' | 'png') {
    const plotly = await loadPlotly();
    const t = performance.now();
    const out = await plotly.toImage(st.gd as never, { format, width: 1200, height: 450, scale: format === 'png' ? 2 : 1 });
    return { ms: performance.now() - t, bytes: out.length };
  },
  unmount() {
    st.root?.unmount();
    st.host?.remove();
    st.root = null;
    st.host = null;
    st.gd = null;
  },
  gc,
  heapBytes,
  svgNodes: () => document.querySelectorAll('.js-plotly-plot svg *').length,
  env() {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl');
    const ext = gl?.getExtension('WEBGL_debug_renderer_info');
    return {
      userAgent: navigator.userAgent, hardwareConcurrency: navigator.hardwareConcurrency,
      deviceMemoryGB: (navigator as unknown as { deviceMemory?: number }).deviceMemory ?? null,
      webglRenderer: gl && ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : null,
      preciseMemory: heapBytes() !== null, gcExposed: typeof (window as unknown as { gc?: unknown }).gc === 'function',
    };
  },
};

declare global {
  interface Window {
    __bench: typeof api;
  }
}
window.__bench = api;
document.title += ' [ready]';

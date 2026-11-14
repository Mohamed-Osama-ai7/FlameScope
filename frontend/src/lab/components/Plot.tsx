import { lazy, Suspense, useRef } from 'react';
import type { Data, Layout, PlotMouseEvent } from 'plotly.js';
import { loadPlotly } from '../plotly';
import { PLOT_CONFIG } from '../plotConfig';

/** Plotly + react-plotly.js are loaded lazily so the initial bundle stays small. SVG traces only. */
const LazyPlot = lazy(async () => {
  const [plotly, factory] = await Promise.all([loadPlotly(), import('react-plotly.js/factory')]);
  return { default: factory.default(plotly) };
});

export async function exportImage(gd: HTMLElement, format: 'svg' | 'png', filename: string, height: number) {
  const plotly = await loadPlotly();
  await plotly.downloadImage(gd as never, { format, filename, width: 1200, height: Math.max(420, height), scale: format === 'png' ? 2 : 1 });
}

interface Props {
  data: Data[];
  layout: Partial<Layout>;
  label: string;
  onSelect?: (recordKey: string) => void;
  onReady?: (gd: HTMLElement) => void;
}

export function Plot({ data, layout, label, onSelect, onReady }: Props) {
  const reduced = useRef(typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  return (
    <div className="plot-wrap" role="group" aria-label={label}>
      <Suspense fallback={<div className="plot-loading" role="status" style={{ height: layout.height ?? 420 }}>Loading chart engine…</div>}>
        <LazyPlot
          data={data}
          layout={{ ...layout, autosize: true, transition: reduced.current ? undefined : { duration: 0, easing: 'linear' } }}
          config={{ ...PLOT_CONFIG, modeBarButtonsToRemove: [...(PLOT_CONFIG.modeBarButtonsToRemove ?? [])] }}
          useResizeHandler
          style={{ width: '100%', height: layout.height ?? 420 }}
          onInitialized={(_fig, gd) => onReady?.(gd)}
          onUpdate={(_fig, gd) => onReady?.(gd)}
          onClick={(e: Readonly<PlotMouseEvent>) => {
            const key = e.points?.[0]?.customdata;
            if (typeof key === 'string') onSelect?.(key);
          }}
        />
      </Suspense>
    </div>
  );
}

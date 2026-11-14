import type * as PlotlyTypes from 'plotly.js';

/**
 * The single place that names the Plotly engine. `plotly.js` here is an npm alias for the cartesian-only build
 * (`"plotly.js": "npm:plotly.js-cartesian-dist-min@<version>"`), so the full engine is never installed or bundled.
 * The engine is lazy-loaded; types come from @types/plotly.js.
 */
export type PlotlyEngine = typeof PlotlyTypes;

export function loadPlotly(): Promise<PlotlyEngine> {
  return import('plotly.js').then((m) => {
    const mod = m as unknown as { default?: PlotlyEngine };
    return mod.default ?? (m as unknown as PlotlyEngine);
  });
}

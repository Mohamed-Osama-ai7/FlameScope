import type { Config } from 'plotly.js';

/**
 * Plotly configuration shared by every chart.
 *
 * Plotly 4 changed the default of `showSendToCloud` to true: an "Upload to Cloud" modebar button that posts the
 * chart data to Plotly's cloud service. Verified in the bundle source: the default is false in 3.7.0 and true in
 * 4.2.0 / 4.3.0. It is disabled explicitly for every engine version, and the button is also removed from the
 * modebar as a second guard (see tests/unit/plot-config.test.ts and the e2e modebar test).
 */
export const PLOT_CONFIG: Partial<Config> = {
  displaylogo: false,
  responsive: true,
  scrollZoom: false,
  showSendToCloud: false,
  modeBarButtonsToRemove: ['select2d', 'lasso2d', 'toImage', 'sendDataToCloud'],
};

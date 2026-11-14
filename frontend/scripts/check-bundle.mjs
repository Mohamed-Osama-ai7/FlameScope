// Usage: node scripts/check-bundle.mjs [dist-dir]
// Verifies the production bundle contains exactly one Plotly engine, that it is the cartesian-only build, and that
// no code from the full plotly.js engine (geo, 3D, maps, Sankey, polar, ...) is present. Exits non-zero on failure.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { join } from 'node:path';

const dist = process.argv[2] ?? 'dist';
const assets = join(dist, 'assets');
const files = readdirSync(assets).filter((f) => f.endsWith('.js'));
const info = files.map((f) => {
  const buf = readFileSync(join(assets, f));
  return { f, text: buf.toString('utf-8'), raw: buf.length, gz: gzipSync(buf, { level: 9 }).length };
});

// A trace is "registered" when its module declares moduleType:"trace" with that name.
const FULL_ENGINE_ONLY = ['scattergeo', 'choropleth', 'scattermapbox', 'scattermap', 'densitymap', 'scatter3d', 'surface', 'mesh3d', 'cone',
  'streamtube', 'volume', 'isosurface', 'sankey', 'parcoords', 'parcats', 'splom', 'scatterpolar', 'barpolar', 'sunburst', 'treemap',
  'icicle', 'funnelarea', 'indicator', 'table', 'waterfall', 'carpet'];
const registered = (text, name) => new RegExp(`moduleType:"trace",name:"${name}"|name:"${name}",basePlotModule`).test(text);

const plotly = info.filter((x) => /scatter|moduleType:"trace"/.test(x.text) && x.raw > 500_000);
const problems = [];
if (plotly.length !== 1) problems.push(`expected exactly 1 Plotly chunk, found ${plotly.length}`);
for (const x of info) for (const t of FULL_ENGINE_ONLY) if (registered(x.text, t)) problems.push(`${x.f} registers non-cartesian trace "${t}"`);
for (const x of info) for (const marker of ['maplibre-gl', 'mapbox-gl', 'gl-plot3d', 'regl-scatter2d']) if (x.text.includes(marker)) problems.push(`${x.f} contains "${marker}"`);

const eng = plotly[0];
const cloudDefault = eng ? /showSendToCloud:\{valType:"boolean",dflt:(!0|!1)\}/.exec(eng.text)?.[1] : undefined;
const report = {
  assets: info.map(({ f, raw, gz }) => ({ file: f, rawKB: Math.round(raw / 1024), gzipKB: Math.round(gz / 1024) })),
  plotlyChunks: plotly.length,
  plotlyRawKB: eng ? Math.round(eng.raw / 1024) : null,
  plotlyGzipKB: eng ? Math.round(eng.gz / 1024) : null,
  cartesianTracesPresent: eng ? ['scatter', 'scattergl', 'bar', 'box', 'heatmap', 'violin'].filter((t) => registered(eng.text, t)) : [],
  bundledEngineShowSendToCloudDefault: cloudDefault === '!0' ? true : cloudDefault === '!1' ? false : 'not found',
  distTotalKB: Math.round(info.reduce((a, x) => a + x.raw, 0) / 1024),
  problems,
};
console.log(JSON.stringify(report, null, 2));
void statSync;
process.exit(problems.length ? 1 : 0);

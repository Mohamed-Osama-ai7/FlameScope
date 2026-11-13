// Usage: node tests/bench/summarize.mjs <label1> [label2 ...] [--browser chromium]
// Prints markdown comparison tables from tests/bench/__results__/*.json (median / p95, ms unless stated).
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const bi = args.indexOf('--browser');
const browser = bi >= 0 ? args.splice(bi, 2)[1] : 'chromium';
const labels = args;
const load = (kind, label) => {
  const f = join(here, '__results__', `${kind}-${label}-${browser}.json`);
  return existsSync(f) ? JSON.parse(readFileSync(f, 'utf-8')) : null;
};
const fmt = (s) => (s && typeof s === 'object' ? `${s.median} / ${s.p95}` : String(s ?? 'n/a'));

const renders = labels.map((l) => [l, load('render', l)]);
const renderers = new Set();
for (const [, r] of renders) if (r) for (const k of Object.keys(r)) if (/^scatter(gl)?_\d+$/.test(k)) renderers.add(k.split('_')[0]);

for (const renderer of renderers) {
  console.log(`\n### Synthetic render (${renderer}), ${browser}: median / p95 ms\n`);
  const metrics = [
    ['Initial render → ready', (r) => r.initialRenderToReadyMs], ['Initial render → painted', (r) => r.initialRenderToPaintMs],
    ['Figure spec build', (r) => r.specMs], ['Filter update → ready', (r) => r.filterUpdateToReadyMs],
    ['Selection highlight → ready', (r) => r.selectUpdateToReadyMs], ['Export SVG', (r) => r.exportSvgMs], ['Export PNG', (r) => r.exportPngMs],
    ['Retained JS heap per mount (MB)', (r) => r.retainedHeapMBPerMount], ['Retained DOM nodes per mount', (r) => r.retainedDomNodesPerMount],
  ];
  for (const size of [1000, 10000, 50000]) {
    console.log(`\n**${size.toLocaleString()} points**\n`);
    console.log(`| Metric | ${labels.join(' | ')} |\n|---|${labels.map(() => '---').join('|')}|`);
    for (const [name, pick] of metrics) {
      const cells = renders.map(([, r]) => (r && r[`${renderer}_${size}`] ? fmt(pick(r[`${renderer}_${size}`])) : 'n/a'));
      console.log(`| ${name} | ${cells.join(' | ')} |`);
    }
    const leaks = renders.map(([, r]) => (r && r[`${renderer}_${size}`] ? JSON.stringify(r[`${renderer}_${size}`].leakCheck) : 'n/a'));
    console.log(`| Leak check (after unmount + GC) | ${leaks.join(' | ')} |`);
  }
}

const apps = labels.map((l) => [l, load('app', l)]);
if (apps.some(([, a]) => a)) {
  console.log(`\n### Real FLEX data in the app, ${browser}: median / p95 ms\n`);
  console.log(`| Metric | ${labels.join(' | ')} |\n|---|${labels.map(() => '---').join('|')}|`);
  const rows = [
    ['Cold load → shell', (a) => a.coldLoad?.shellMs], ['Cold load → first chart drawn', (a) => a.coldLoad?.firstChartDrawnMs],
    ['DOMContentLoaded', (a) => a.coldLoad?.domContentLoadedMs], ['First contentful paint', (a) => a.coldLoad?.firstContentfulPaintMs],
    ['View switch → chart', (a) => a.interactions?.viewSwitchToChartMs], ['Filter toggle → chart', (a) => a.interactions?.filterToggleToChartMs],
    ['Selection → inspector open', (a) => a.interactions?.selectionToInspectorOpenMs], ['Inspector close', (a) => a.interactions?.inspectorCloseMs],
    ['CSV export (end-to-end)', (a) => a.exports?.csvMs], ['SVG export (end-to-end)', (a) => a.exports?.svgMs], ['PNG export (end-to-end)', (a) => a.exports?.pngMs],
  ];
  for (const [name, pick] of rows) console.log(`| ${name} | ${apps.map(([, a]) => (a ? fmt(pick(a)) : 'n/a')).join(' | ')} |`);
  console.log(`| Transferred (KB) / Plotly chunk (KB) | ${apps.map(([, a]) => (a?.coldLoad ? `${a.coldLoad.resourcesTransferredKB} / ${a.coldLoad.plotlyChunkKB}` : 'n/a')).join(' | ')} |`);
  console.log(`| JS heap before → after 20 reps (MB) | ${apps.map(([, a]) => (a?.interactions ? `${a.interactions.heapMBBefore} → ${a.interactions.heapMBAfterRepetitions}` : 'n/a')).join(' | ')} |`);
}

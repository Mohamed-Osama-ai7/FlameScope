import { test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stat } from './stats';

/**
 * SYNTHETIC rendering benchmarks through the real <Plot> + scatterFigure path (bench/bench.tsx).
 * Warm-up runs are discarded; each metric reports median and p95 over the repetitions in `REPS`.
 * On Chromium, heap and DOM-node figures come from the DevTools Protocol with forced GC;
 * other engines report only wall-clock timings.
 */
const HERE = dirname(fileURLToPath(import.meta.url));
const LABEL = process.env.BENCH_LABEL ?? 'unlabelled';
const SIZES = [1_000, 10_000, 50_000];
const REPS: Record<number, { render: number; update: number; exp: number }> = {
  1_000: { render: 15, update: 15, exp: 10 },
  10_000: { render: 10, update: 10, exp: 5 },
  50_000: { render: 5, update: 5, exp: 3 },
};
const WARMUP = 2;
const RENDERERS = ['scatter'] as const; // the cartesian-only engine has no WebGL trace to compare
const UNAVAILABLE = 'unavailable (Chromium only)';

const results: Record<string, unknown> = { label: LABEL, warmup: WARMUP, reps: REPS };

test.afterAll(() => {
  const dir = join(HERE, '__results__');
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `render-${LABEL}-${process.env.BENCH_BROWSERS ?? 'chromium'}.json`);
  writeFileSync(file, JSON.stringify(results, null, 2));
  console.log(`[bench] wrote ${file}`);
});

for (const renderer of RENDERERS) {
  for (const n of SIZES) {
    test(`render ${renderer} n=${n}`, async ({ page, browserName }) => {
      test.setTimeout(300_000);
      await page.goto('http://127.0.0.1:4190/');
      await page.waitForFunction(() => document.title.includes('[ready]'));
      const prep = await page.evaluate(([c, r]) => window.__bench.prepare(c as number, r as 'scatter'), [n, renderer]);
      if (!prep.synthetic) throw new Error('harness dataset must be flagged synthetic');
      if (!results.env) results.env = { browser: browserName, ...(await page.evaluate(() => window.__bench.env())) };
      const reps = REPS[n];

      const cdp = browserName === 'chromium' ? await page.context().newCDPSession(page) : null;
      if (cdp) await cdp.send('Performance.enable');
      const metrics = async (collect: boolean) => {
        if (!cdp) return null;
        if (collect) await cdp.send('HeapProfiler.collectGarbage');
        const { metrics: m } = await cdp.send('Performance.getMetrics');
        return Object.fromEntries(m.map((x) => [x.name, x.value])) as Record<string, number>;
      };

      // Warm-up: the first call also downloads and parses the lazy Plotly chunk.
      for (let i = 0; i < WARMUP; i++) await page.evaluate(() => window.__bench.mount());
      await page.evaluate(() => window.__bench.unmount());
      const initial = await metrics(true);

      // Initial render (fresh root each time) with a script/layout/style breakdown and retained heap/DOM.
      const spec: number[] = [], plot: number[] = [], paint: number[] = [];
      const heapMB: number[] = [], nodes: number[] = [];
      let points = 0, svgNodes = 0;
      for (let i = 0; i < reps.render; i++) {
        await page.evaluate(() => window.__bench.unmount());
        const base = await metrics(true);
        const m = await page.evaluate(() => window.__bench.mount());
        const kept = await metrics(true);
        spec.push(m.specMs); plot.push(m.plotMs); paint.push(m.paintMs); points = m.points;
        if (base && kept) {
          heapMB.push((kept.JSHeapUsedSize - base.JSHeapUsedSize) / 1048576);
          nodes.push(kept.Nodes - base.Nodes);
        }
        svgNodes = await page.evaluate(() => window.__bench.svgNodes());
      }

      // Linked-view style updates on the mounted chart (filter toggle, selection highlight).
      const filt: number[] = [], filtPaint: number[] = [], sel: number[] = [], selPaint: number[] = [];
      for (let i = 0; i < WARMUP; i++) {
        await page.evaluate(() => window.__bench.filterUpdate());
        await page.evaluate(() => window.__bench.selectUpdate());
      }
      for (let i = 0; i < reps.update; i++) {
        const f = await page.evaluate(() => window.__bench.filterUpdate());
        filt.push(f.plotMs); filtPaint.push(f.paintMs);
        const s = await page.evaluate(() => window.__bench.selectUpdate());
        sel.push(s.plotMs); selPaint.push(s.paintMs);
      }
      // Re-mount at full size for the export measurements.
      await page.evaluate(() => window.__bench.mount());
      const svg: number[] = [], png: number[] = [];
      let svgBytes = 0, pngBytes = 0;
      for (let i = 0; i < WARMUP - 1; i++) await page.evaluate(() => window.__bench.exportImage('svg'));
      for (let i = 0; i < reps.exp; i++) {
        const a = await page.evaluate(() => window.__bench.exportImage('svg'));
        svg.push(a.ms); svgBytes = a.bytes;
        const b = await page.evaluate(() => window.__bench.exportImage('png'));
        png.push(b.ms); pngBytes = b.bytes;
      }
      // Leak check: heap and DOM nodes after unmount + GC versus the state before the first measured mount.
      await page.evaluate(() => window.__bench.unmount());
      const final = await metrics(true);
      const r1 = (x: number) => Math.round(x * 10) / 10;

      const row = {
        points, svgNodes,
        specMs: stat(spec), initialRenderToReadyMs: stat(plot), initialRenderToPaintMs: stat(paint),
        filterUpdateToReadyMs: stat(filt), filterUpdateToPaintMs: stat(filtPaint),
        selectUpdateToReadyMs: stat(sel), selectUpdateToPaintMs: stat(selPaint),
        exportSvgMs: stat(svg), exportPngMs: stat(png),
        svgExportKB: Math.round(svgBytes / 1024), pngExportKB: Math.round(pngBytes / 1024),
        retainedHeapMBPerMount: heapMB.length ? stat(heapMB) : UNAVAILABLE,
        retainedDomNodesPerMount: nodes.length ? stat(nodes) : UNAVAILABLE,
        leakCheck: initial && final
          ? { heapMBAfterUnmountVsBefore: r1((final.JSHeapUsedSize - initial.JSHeapUsedSize) / 1048576), domNodesAfterUnmountVsBefore: final.Nodes - initial.Nodes }
          : UNAVAILABLE,
      };
      (results as Record<string, unknown>)[`${renderer}_${n}`] = row;
      console.log(`[bench] ${renderer} n=${n} ${JSON.stringify({ ready: row.initialRenderToReadyMs, paint: row.initialRenderToPaintMs, filter: row.filterUpdateToReadyMs, select: row.selectUpdateToReadyMs, svg: row.exportSvgMs, png: row.exportPngMs, leak: row.leakCheck })}`);
    });
  }
}

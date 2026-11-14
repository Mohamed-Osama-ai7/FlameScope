import type { Page } from '@playwright/test';

export async function openLab(page: Page, hash = '', theme: 'light' | 'dark' = 'dark') {
  await page.addInitScript((t) => {
    try {
      localStorage.setItem('flamescope-theme', t);
    } catch {
      /* ignore */
    }
  }, theme);
  await page.goto(`/${hash ? `#${hash}` : ''}`);
  await page.getByRole('navigation', { name: 'Lab sections' }).waitFor();
}

/** Wait until Plotly has drawn at least one chart (SVG scatter layer present). */
export async function waitForPlot(page: Page) {
  await page.locator('.js-plotly-plot .scatterlayer, .js-plotly-plot .boxlayer, .js-plotly-plot .heatmaplayer').first().waitFor({ timeout: 30_000 });
  await page.waitForTimeout(400);
}

/** Pixel position (page coordinates) of the first plotted point of the first scatter chart. */
export async function firstPointPosition(page: Page) {
  return page.evaluate(() => {
    const gd = document.querySelector('.js-plotly-plot') as unknown as {
      data: { x: number[]; y: number[]; customdata: string[]; xaxis?: string; yaxis?: string }[];
      _fullLayout: Record<string, { _offset: number; l2p: (v: number) => number }>;
      getBoundingClientRect: () => DOMRect;
    };
    const tr = gd.data.find((d) => Array.isArray(d.customdata) && d.customdata.length && !String(d.customdata[0]).startsWith('SELECTED'))!;
    const xa = gd._fullLayout[(tr.xaxis ?? 'x').replace('x', 'xaxis')];
    const ya = gd._fullLayout[(tr.yaxis ?? 'y').replace('y', 'yaxis')];
    const box = gd.getBoundingClientRect();
    return { x: box.left + xa._offset + xa.l2p(tr.x[0]), y: box.top + ya._offset + ya.l2p(tr.y[0]), key: tr.customdata[0] };
  });
}

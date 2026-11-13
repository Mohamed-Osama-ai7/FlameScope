import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { PLOT_CONFIG } from '../../src/lab/plotConfig';

describe('Plotly config guards', () => {
  it('disables the cloud-upload feature that Plotly 4 enables by default', () => {
    expect(PLOT_CONFIG.showSendToCloud).toBe(false);
    expect(PLOT_CONFIG.modeBarButtonsToRemove).toContain('sendDataToCloud');
  });
  it('keeps the toolbar free of unsupported actions', () => {
    expect(PLOT_CONFIG.modeBarButtonsToRemove).toEqual(expect.arrayContaining(['select2d', 'lasso2d', 'toImage']));
    expect(PLOT_CONFIG.displaylogo).toBe(false);
  });
});

describe('single cartesian engine', () => {
  const pkg = JSON.parse(readFileSync('package.json', 'utf-8'));
  it('declares one aliased cartesian engine, no full plotly.js and no second engine', () => {
    expect(pkg.dependencies['plotly.js']).toMatch(/^npm:plotly\.js-cartesian-dist-min@\d+\.\d+\.\d+$/);
    const all = { ...pkg.dependencies, ...pkg.devDependencies };
    expect(Object.keys(all).filter((n) => /^plotly\.js/.test(n))).toEqual(['plotly.js']);
    for (const banned of ['echarts', 'd3', 'plotly.js-dist', 'plotly.js-dist-min', 'plotly.js-cartesian-dist-min']) expect(all[banned]).toBeUndefined();
  });
  it('the installed engine package is the cartesian build', () => {
    const installed = JSON.parse(readFileSync('node_modules/plotly.js/package.json', 'utf-8'));
    expect(installed.name).toBe('plotly.js-cartesian-dist-min');
    expect(installed.main).toBe('plotly-cartesian.min.js');
  });
  it('Playwright packages are aligned', () => {
    const v = (n: string) => JSON.parse(readFileSync(`node_modules/${n}/package.json`, 'utf-8')).version as string;
    expect(new Set([v('@playwright/test'), v('playwright'), v('playwright-core')]).size).toBe(1);
  });
});

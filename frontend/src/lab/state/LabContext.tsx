import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { ChartTheme } from '../charts/specs';
import { SERIES } from '../charts/specs';
import type { Filters } from '../data/selectors';
import { defaultFilters } from '../data/selectors';
import type { FlexRecord, LabDataset } from '../data/types';

export type ThemeMode = 'light' | 'dark';

interface LabState {
  dataset: LabDataset;
  byKey: Map<string, FlexRecord>;
  filters: Filters;
  setFilters: (f: Filters) => void;
  resetFilters: () => void;
  selectedKey: string | null;
  select: (key: string | null, opts?: { open?: boolean }) => void;
  inspectorOpen: boolean;
  closeInspector: () => void;
  theme: ThemeMode;
  setTheme: (t: ThemeMode) => void;
  chartTheme: ChartTheme;
}

const Ctx = createContext<LabState | null>(null);

function initialTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem('flamescope-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function readTheme(mode: ThemeMode): ChartTheme {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    mode,
    bg: v('--surface-1', mode === 'dark' ? '#101a26' : '#ffffff'),
    fg: v('--text-1', mode === 'dark' ? '#eef2f7' : '#0b1220'),
    muted: v('--text-2', mode === 'dark' ? '#a9b6c4' : '#4a5566'),
    grid: v('--grid', mode === 'dark' ? '#223042' : '#e6e9ee'),
    axis: v('--axis', mode === 'dark' ? '#5b6b7d' : '#8a93a0'),
    series: SERIES[mode],
    font: 'Inter, "Segoe UI", system-ui, sans-serif',
  };
}

export function LabProvider({ dataset, children }: { dataset: LabDataset; children: ReactNode }) {
  const byKey = useMemo(() => new Map(dataset.records.map((r) => [r.record_key, r])), [dataset]);
  const [filters, setFilters] = useState<Filters>(() => defaultFilters(dataset.records));
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [theme, setThemeState] = useState<ThemeMode>(initialTheme);
  const [chartTheme, setChartTheme] = useState<ChartTheme>(() => readTheme(theme));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('flamescope-theme', theme);
    } catch {
      /* storage unavailable */
    }
    setChartTheme(readTheme(theme));
  }, [theme]);

  const select = useCallback((key: string | null, opts: { open?: boolean } = {}) => {
    setSelectedKey(key);
    if (key && opts.open !== false) setInspectorOpen(true);
  }, []);

  const value: LabState = {
    dataset, byKey, filters, setFilters,
    resetFilters: () => setFilters(defaultFilters(dataset.records)),
    selectedKey, select, inspectorOpen, closeInspector: () => setInspectorOpen(false),
    theme, setTheme: setThemeState, chartTheme,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLab(): LabState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useLab outside LabProvider');
  return v;
}

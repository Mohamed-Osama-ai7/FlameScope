import { useEffect, useState } from 'react';
import { EvidenceInspector } from './lab/components/EvidenceInspector';
import { FilterBar } from './lab/components/FilterBar';
import { loadDataset } from './lab/data/load';
import type { LabDataset } from './lab/data/types';
import { Combustion } from './lab/sections/Combustion';
import { Conditions } from './lab/sections/Conditions';
import { Observations } from './lab/sections/Observations';
import { Outcomes } from './lab/sections/Outcomes';
import { Overview } from './lab/sections/Overview';
import { Quality } from './lab/sections/Quality';
import { LabProvider, useLab } from './lab/state/LabContext';

const API = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

const SECTIONS = [
  { id: 'overview', label: 'Overview' },
  { id: 'combustion', label: 'Combustion Explorer' },
  { id: 'conditions', label: 'Conditions Explorer' },
  { id: 'outcomes', label: 'Outcomes & Extinction' },
  { id: 'quality', label: 'Data Quality & Evidence' },
  { id: 'observations', label: 'Observations' },
] as const;
type SectionId = (typeof SECTIONS)[number]['id'];

function parseHash(): { section: SectionId; param?: string } {
  const [s, ...rest] = window.location.hash.replace(/^#/, '').split('/');
  const section = (SECTIONS.find((x) => x.id === s)?.id ?? 'overview') as SectionId;
  return { section, param: rest.length ? decodeURIComponent(rest.join('/')) : undefined };
}

function ApiStatus() {
  const [state, setState] = useState<'checking' | 'online' | 'offline'>('checking');
  useEffect(() => {
    const ctl = new AbortController();
    fetch(`${API}/health`, { signal: ctl.signal }).then((r) => setState(r.ok ? 'online' : 'offline')).catch(() => setState('offline'));
    return () => ctl.abort();
  }, []);
  return <span className="status-pill" title="FastAPI backend health (the lab itself uses the exported static dataset)"><i className={state} aria-hidden="true" />API {state}</span>;
}

function Shell() {
  const { theme, setTheme, dataset } = useLab();
  const [route, setRoute] = useState(parseHash);
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  useEffect(() => {
    document.title = `${SECTIONS.find((s) => s.id === route.section)?.label} · FlameScope Lab`;
  }, [route.section]);

  return (
    <div className="app">
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <div className="brand"><div className="mark" aria-hidden="true">FS</div>
          <div><span className="eyebrow">UNDERFITTED · SCIENTIFIC EXPLORATION LAB</span><h1>FlameScope</h1></div></div>
        <div className="top-actions">
          <ApiStatus />
          <button type="button" className="ghost" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? '☀ Light' : '☾ Dark'}
          </button>
        </div>
      </header>
      <nav className="tabs" aria-label="Lab sections">
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} aria-current={route.section === s.id ? 'page' : undefined}>{s.label}</a>
        ))}
      </nav>
      <div className="banner" role="note">
        Independent research prototype · not NASA-endorsed · not a fire-safety tool · descriptive exploration of NASA-reported FLEX values (analysis v{dataset.analysis_version}).
      </div>
      <div className="layout">
        <div className={`filters-wrap ${filtersOpen ? 'open' : ''}`}>
          <button type="button" className="filters-toggle" aria-expanded={filtersOpen} aria-controls="filters-panel" onClick={() => setFiltersOpen(!filtersOpen)}>
            {filtersOpen ? 'Hide filters' : 'Show filters'}
          </button>
          <div id="filters-panel"><FilterBar /></div>
        </div>
        <main id="main" tabIndex={-1}>
          {route.section === 'overview' && <Overview />}
          {route.section === 'combustion' && <Combustion />}
          {route.section === 'conditions' && <Conditions />}
          {route.section === 'outcomes' && <Outcomes />}
          {route.section === 'quality' && <Quality focusRule={route.param} />}
          {route.section === 'observations' && <Observations />}
        </main>
      </div>
      <footer className="foot">
        <span>FLAMESCOPE / UNDERFITTED</span>
        <span>Source: NASA PSI-69 (DOI {dataset.provenance.doi}) · NASA/TP-2015-216046 · raw SHA-256 {dataset.provenance.raw_sha256.slice(0, 12)}…</span>
      </footer>
      <EvidenceInspector />
    </div>
  );
}

export default function App() {
  const [dataset, setDataset] = useState<LabDataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    loadDataset().then(setDataset).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <main className="fatal" role="alert"><h1>FlameScope Lab</h1><p>Dataset could not be loaded: {error}</p></main>;
  if (!dataset) return <main className="fatal" aria-busy="true"><p>Loading verified FLEX dataset…</p></main>;
  return <LabProvider dataset={dataset}><Shell /></LabProvider>;
}

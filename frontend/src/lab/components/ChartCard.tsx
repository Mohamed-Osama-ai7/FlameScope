import { useRef, useState, type ReactNode } from 'react';
import type { Figure } from '../charts/specs';
import { chartConfig, downloadText } from '../data/export';
import type { ViewData } from '../data/selectors';
import { FIELD_LABEL, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';
import { exportImage, Plot } from './Plot';
import { RecordList } from './RecordList';

interface Props {
  vd: ViewData;
  figure: Figure;
  children?: ReactNode;
  idSuffix?: string;
}

function Reasons({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  return (
    <div className="reasons">
      <span className="eyebrow">{title}</span>
      <ul>{entries.map(([k, n]) => <li key={k}><b>{n}</b> {k}</li>)}</ul>
    </div>
  );
}

export function ChartCard({ vd, figure, children, idSuffix = '' }: Props) {
  const { dataset, filters, select } = useLab();
  const gd = useRef<HTMLElement | null>(null);
  const [status, setStatus] = useState('');
  const v = vd.view;
  const base = `flamescope_${v.id}${idSuffix}_v${dataset.analysis_version}`;
  const id = `chart-${v.id}${idSuffix}`;

  const doImage = async (format: 'svg' | 'png') => {
    if (!gd.current) return setStatus('Chart not ready yet.');
    await exportImage(gd.current, format, base, Number(figure.layout.height ?? 460));
    setStatus(`${format.toUpperCase()} exported (${base}.${format}).`);
  };

  return (
    <section className="card chart-card" aria-labelledby={`${id}-title`} data-view={v.id}>
      <header className="card-head">
        <span className="eyebrow">{v.analysis ? `Analysis ${v.analysis} · v${dataset.analysis_version}` : `Rule-based view · v${dataset.analysis_version}`}</span>
        <h3 id={`${id}-title`}>{v.title}</h3>
        <p className="question">{v.question}</p>
      </header>
      <dl className="meta">
        <div><dt>Variables</dt><dd>{v.x ? `${FIELD_LABEL[v.x]} (${dataset.units[v.x]}) → ` : ''}{FIELD_LABEL[v.y]} ({dataset.units[v.y]})</dd></div>
        <div><dt>Panels</dt><dd>{vd.panels.map((p) => `${p.fuel} · ${SUPPORT_LABEL[p.support]} (n=${p.records.length})`).join('; ') || 'none selected'}</dd></div>
        <div><dt>Shown / eligible</dt><dd data-testid={`${id}-counts`}>{vd.shown.length} of {vd.eligible.length} eligible records ({dataset.records.length} total)</dd></div>
        <div><dt>Eligibility rule</dt><dd>{v.rule}</dd></div>
        <div><dt>Source</dt><dd>NASA PSI-69 (FLEX), DOI {dataset.provenance.doi}; NASA/TP-2015-216046</dd></div>
      </dl>
      <Plot data={figure.data} layout={figure.layout} label={`${v.title}. ${vd.shown.length} records plotted. Use the record table below for an accessible alternative.`}
        onSelect={(k) => select(k)} onReady={(el) => { gd.current = el; }} />
      <div className="exclusions">
        <Reasons title="Outside scientific rule (not plotted)" counts={vd.ineligible} />
        <Reasons title="Hidden by your visual filters" counts={vd.excludedByFilter} />
      </div>
      <div className="limits" role="note">
        <span className="eyebrow">Limitations</span>
        <ul>{v.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </div>
      {children}
      <div className="actions" aria-label="Chart exports">
        <button type="button" onClick={() => doImage('svg')}>Export SVG</button>
        <button type="button" onClick={() => doImage('png')}>Export PNG</button>
        <button type="button" onClick={() => {
          downloadText(`${base}_config.json`, JSON.stringify(chartConfig(dataset, vd, filters), null, 2), 'application/json');
          setStatus('Chart configuration JSON exported.');
        }}>Export config JSON</button>
        <span className="status" role="status" aria-live="polite">{status}</span>
      </div>
      <details className="table-alt">
        <summary>Plotted records as a table ({vd.shown.length})</summary>
        <RecordList records={vd.shown} fields={[v.x, v.y].filter(Boolean) as never} />
      </details>
    </section>
  );
}

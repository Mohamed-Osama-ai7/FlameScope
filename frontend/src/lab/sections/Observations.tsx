import { useState } from 'react';
import { RecordTable } from '../components/RecordTable';
import { analysisSummary, downloadText, provenanceBlock } from '../data/export';
import { useLab } from '../state/LabContext';

export function Observations() {
  const { dataset, filters } = useLab();
  const [status, setStatus] = useState('');
  const v = dataset.analysis_version;
  return (
    <div className="stack">
      <RecordTable />
      <section className="card" aria-labelledby="exp-title">
        <header className="card-head">
          <span className="eyebrow">Reproducibility</span>
          <h3 id="exp-title">Analysis summary and provenance exports</h3>
          <p className="question">Statistics come from the approved Python v{v} analysis; the browser does not recompute them.
            Regenerate with <code>python backend/scripts/run_flex_analysis.py</code> and <code>python backend/scripts/export_lab_dataset.py</code>.</p>
        </header>
        <div className="actions">
          <button type="button" onClick={() => {
            downloadText(`flamescope_flex_analysis_summary_v${v}.json`, JSON.stringify(analysisSummary(dataset, filters), null, 2), 'application/json');
            setStatus('Analysis summary JSON exported (aggregated Python strata statistics).');
          }}>Export analysis summary JSON</button>
          <button type="button" onClick={() => {
            downloadText(`flamescope_flex_provenance_v${v}.json`, JSON.stringify(provenanceBlock(dataset), null, 2), 'application/json');
            setStatus('Provenance metadata JSON exported.');
          }}>Export provenance JSON</button>
          <span className="status" role="status" aria-live="polite">{status}</span>
        </div>
        <p className="small muted">PDF export is not offered: its output quality has not been verified.</p>
      </section>
    </div>
  );
}

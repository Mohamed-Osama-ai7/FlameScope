import { strataFor } from '../data/selectors';
import { useLab } from '../state/LabContext';
import { FIELD_LABEL, SUPPORT_LABEL } from '../data/types';
import type { NumericField } from '../data/types';

const ANALYSES = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6'] as const;

function formatRho(value: number | null): string {
  return value === null ? 'Not reported (n < 5 or no variation)' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

/** Displays statistics from the versioned Python export; the browser does not recompute analysis. */
export function AnalysisResults() {
  const { dataset, filters, select } = useLab();
  const analyses = ANALYSES.map((analysis) => ({
    analysis,
    rows: strataFor(dataset, analysis, filters.supportModes, filters.fuels),
  }));
  const visible = analyses.filter(({ rows }) => rows.length > 0);

  return <div className="stack">
    <section className="card" aria-labelledby="analysis-results-title">
      <header className="card-head">
        <span className="eyebrow">Analysis Results · Python export v{dataset.analysis_version}</span>
        <h2 id="analysis-results-title">Published run-level summaries</h2>
        <p className="question">Descriptive Spearman rank correlations and sample sizes are loaded from the versioned analysis export. The browser does not fit or infer results.</p>
      </header>
      <div className="callout" role="note">
        <b>Interpretation limits.</b> ρ is descriptive; no p-values or multiple-comparison correction are supplied. A missing ρ means n &lt; 5 or no variation. The reported burning-rate constant has no uncertainty in this dataset. Results describe observational test strata and do not establish causation.
      </div>
      {visible.length === 0 ? <p className="explorer-state">No analysis strata match the selected fuels and support modes.</p> : visible.map(({ analysis, rows }) => <section className="analysis-result-group" key={analysis} aria-labelledby={`analysis-${analysis}`}>
        <h3 id={`analysis-${analysis}`}>{analysis} <span className="small muted">{rows.length} matching strata</span></h3>
        <div className="table-scroll"><table className="data">
          <thead><tr><th scope="col">Fuel</th><th scope="col">Support</th><th scope="col">Variables</th><th scope="col">Stratum conditions</th><th scope="col">n</th><th scope="col">Spearman ρ</th><th scope="col">Sensitivity</th><th scope="col">Source PSI rows</th><th scope="col">Analysis note</th></tr></thead>
          <tbody>{rows.map((row, index) => <tr key={`${row.analysis}-${row.fuel}-${index}`}>
            <td>{row.fuel}</td>
            <td>{SUPPORT_LABEL[String(row.stratum.support_mode) as keyof typeof SUPPORT_LABEL] ?? String(row.stratum.support_mode)}</td>
            <td>{[row.x, row.y].map((field) => field in FIELD_LABEL ? `${FIELD_LABEL[field as NumericField]} (${dataset.units[field as NumericField]})` : field).join(' → ')}</td>
            <td>{Object.entries(row.stratum).filter(([key]) => key !== 'support_mode').map(([key, value]) => `${key}=${value ?? 'unknown'}`).join('; ') || '—'}</td>
            <td className="num">{row.n}</td>
            <td className="num">{formatRho(row.rho_spearman)}</td>
            <td>{row.sensitivity_rows.length ? `PSI ${row.sensitivity_rows.join(', ')}; ρ without rows: ${formatRho(row.rho_without_sensitivity_rows)}` : 'No tagged sensitivity rows'}</td>
            <td>{row.psi_rows.map((psiRow, index) => {
              const record = dataset.records.find((item) => item.psi_row === psiRow);
              return <span key={psiRow}>{index > 0 ? ', ' : ''}{record ? <button className="text-button" type="button" onClick={() => select(record.record_key)} aria-label={`Inspect PSI row ${psiRow} evidence`}>{psiRow}</button> : psiRow}</span>;
            })}</td>
            <td className="small">{row.note}</td>
          </tr>)}</tbody>
        </table></div>
      </section>)}
      <p className="small muted">Source: NASA PSI-69, DOI <a href={`https://doi.org/${dataset.provenance.doi}`} target="_blank" rel="noreferrer">{dataset.provenance.doi}</a>; supporting report <a href={dataset.provenance.report_url} target="_blank" rel="noreferrer">NASA/TP-2015-216046</a>. PSI row numbers open their evidence inspector.</p>
    </section>
  </div>;
}

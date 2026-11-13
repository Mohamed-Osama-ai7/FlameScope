import type { Stratum } from '../data/types';
import { SUPPORT_LABEL } from '../data/types';

function fmt(x: number | null): string {
  return x === null ? '—' : (x >= 0 ? '+' : '') + x.toFixed(2);
}

/** Python v0.2.0 strata statistics (descriptive Spearman rho; never computed in the browser). */
export function StrataTable({ strata, caption }: { strata: Stratum[]; caption: string }) {
  if (!strata.length) return <p className="muted small">No v0.2.0 strata for the current selection.</p>;
  return (
    <details className="strata">
      <summary>{caption} ({strata.length} strata; all shown, none selected)</summary>
      <p className="small muted">ρ = Spearman rank correlation computed in Python (backend/app/analysis/flex_run_level.py). Descriptive only:
        no p-values, no multiple-comparison correction; n ≥ 5 is a reporting floor, not reliability. “—” means n &lt; 5 or no variation.</p>
      <div className="table-scroll"><table className="data">
        <thead><tr><th scope="col">Fuel</th><th scope="col">Support</th><th scope="col">Stratum</th><th scope="col">n</th><th scope="col">ρ</th>
          <th scope="col">Ties x/y</th><th scope="col">Sensitivity rows</th><th scope="col">ρ without them</th><th scope="col">Note</th></tr></thead>
        <tbody>{strata.map((s, i) => (
          <tr key={i}>
            <td>{s.fuel}</td><td>{SUPPORT_LABEL[String(s.stratum.support_mode) as keyof typeof SUPPORT_LABEL] ?? String(s.stratum.support_mode)}</td>
            <td>{Object.entries(s.stratum).filter(([k]) => k !== 'support_mode').map(([k, v]) => `${k}=${v}`).join('; ')}</td>
            <td className="num">{s.n}</td><td className="num">{fmt(s.rho_spearman)}</td>
            <td className="num">{s.n_values_in_x_ties}/{s.n_values_in_y_ties}</td>
            <td>{s.sensitivity_rows.length ? `PSI ${s.sensitivity_rows.join(', ')}` : '—'}</td>
            <td className="num">{s.sensitivity_rows.length ? fmt(s.rho_without_sensitivity_rows) : '—'}</td>
            <td className="small">{s.note}</td>
          </tr>
        ))}</tbody>
      </table></div>
    </details>
  );
}

import { useMemo } from 'react';
import { dextClassLabel } from '../charts/specs';
import { countBy, PRESSURE_INVALID, qualityWarnings } from '../data/selectors';
import { FAMILY_LABEL, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';

function CountTable({ title, counts, label }: { title: string; counts: Record<string, number>; label?: (k: string) => string }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const max = Math.max(...Object.values(counts));
  return (
    <section className="card count-card" aria-label={title}>
      <h3 className="eyebrow">{title}</h3>
      <table className="bars">
        <tbody>
          {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
            <tr key={k}>
              <th scope="row">{label ? label(k) : k}</th>
              <td className="bar-cell"><span className="bar" style={{ width: `${(n / max) * 100}%` }} aria-hidden="true" /></td>
              <td className="num">{n}</td>
            </tr>
          ))}
        </tbody>
        <tfoot><tr><th scope="row">Total records</th><td /><td className="num">{total}</td></tr></tfoot>
      </table>
    </section>
  );
}

export function Overview() {
  const { dataset } = useLab();
  const r = dataset.records;
  const warnings = useMemo(() => qualityWarnings(dataset), [dataset]);
  const s = dataset.scope;
  const tiles = [
    { k: 'Records (PSI-69 rows)', v: s.records },
    { k: 'Unique NASA FLEX tests', v: s.unique_flex_tests },
    { k: 'Unique FLEX identifiers', v: s.unique_identifiers, note: '193F001 appears on two records' },
    { k: 'Tests stated by NASA', v: s.nasa_stated_tests, note: `${s.table_ix_printed_rows} printed in Table IX` },
    { k: 'Printed rows not in PSI', v: s.table_ix_rows_not_in_psi.length, note: s.table_ix_rows_not_in_psi.join(', ') },
    { k: 'Analysis version', v: `v${dataset.analysis_version}`, note: 'approved, audited (docs/11)' },
  ];
  return (
    <div className="section-grid">
      <section className="card hero-card" aria-labelledby="ov-title">
        <span className="eyebrow">Overview · FLEX droplet combustion · NASA PSI-69</span>
        <h2 id="ov-title">What this dataset contains, and what it does not</h2>
        <p className="lead">{dataset.value_origin}</p>
        <div className="tiles">
          {tiles.map((t) => (
            <div className="tile" key={t.k}><span className="tile-v">{t.v}</span><span className="tile-k">{t.k}</span>{t.note && <span className="tile-n">{t.note}</span>}</div>
          ))}
        </div>
        <p className="small muted">Records are PSI rows; each maps to exactly one printed NASA Table IX row. 284 (stated) − 276 (printed) − 2 (not in PSI) is unresolved and not forced to agree.</p>
      </section>
      <CountTable title="Fuel" counts={countBy(r, (x) => x.fuel)} />
      <CountTable title="Support mode (NASA captions)" counts={countBy(r, (x) => x.support_mode)} label={(k) => SUPPORT_LABEL[k as keyof typeof SUPPORT_LABEL]} />
      <CountTable title="Pressure cluster" counts={countBy(r, (x) => x.pressure_cluster ?? PRESSURE_INVALID)} label={(k) => (k === PRESSURE_INVALID ? 'Invalid pressure (FLEX-114)' : k.replace(' nominal', ''))} />
      <CountTable title="Recorded composition family" counts={countBy(r, (x) => x.diluent_family)} label={(k) => FAMILY_LABEL[k as keyof typeof FAMILY_LABEL]} />
      <CountTable title="Test end (NASA)" counts={countBy(r, (x) => x.test_end)} />
      <CountTable title="Extinction-diameter origin" counts={countBy(r, (x) => x.dext_origin)} label={dextClassLabel} />
      <section className="card" aria-labelledby="ov-warn">
        <h3 id="ov-warn" className="eyebrow">Data-quality warnings (counts of records per rule; no composite score)</h3>
        <ul className="warn-list compact">
          {warnings.map((w) => (
            <li key={w.rule + w.label}><a href={`#quality/${encodeURIComponent(w.rule)}`}>{w.label}</a> <span className="count">{w.recordKeys.length || 'source-level'}</span></li>
          ))}
        </ul>
      </section>
      <section className="card" aria-labelledby="ov-unknown">
        <h3 id="ov-unknown" className="eyebrow">Unavailable (shown as UNKNOWN)</h3>
        <ul>{dataset.unknown_fields.map((f) => <li key={f}>{f}</li>)}</ul>
      </section>
    </div>
  );
}

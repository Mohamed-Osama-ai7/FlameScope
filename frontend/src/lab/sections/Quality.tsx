import { useEffect, useMemo } from 'react';
import { qualityWarnings } from '../data/selectors';
import type { NumericField } from '../data/types';
import { FIELD_LABEL, FUELS, NUMERIC_FIELDS } from '../data/types';
import { useLab } from '../state/LabContext';

export const ruleAnchor = (rule: string) => `rule-${rule.replace(/[^a-zA-Z0-9]/g, '-')}`;

export function Quality({ focusRule }: { focusRule?: string }) {
  const { dataset, byKey, select } = useLab();
  const warnings = useMemo(() => qualityWarnings(dataset), [dataset]);

  useEffect(() => {
    if (focusRule) document.getElementById(ruleAnchor(focusRule))?.scrollIntoView({ block: 'start' });
  }, [focusRule]);

  return (
    <div className="stack">
      <section className="card" aria-labelledby="q-warn">
        <header className="card-head">
          <span className="eyebrow">Data quality & evidence · all records, independent of visual filters</span>
          <h3 id="q-warn">Warnings ({warnings.length} rule groups)</h3>
          <p className="question">Every warning links to its documented rule and to each affected record. There is no composite quality score.</p>
        </header>
        <ul className="warn-list" data-testid="warning-list">
          {warnings.map((w) => (
            <li key={w.rule + w.label}>
              <div className="warn-head"><b>{w.label}</b> <a href={`#quality/${encodeURIComponent(w.rule)}`} className="rule-link">rule {w.rule}</a>
                <span className="count">{w.recordKeys.length ? `${w.recordKeys.length} records` : 'source-level'}</span></div>
              {w.recordKeys.length > 0 && (
                <div className="chips">
                  {w.recordKeys.map((k) => {
                    const r = byKey.get(k);
                    return <button key={k} type="button" className="chip" onClick={() => select(k)} aria-label={`Inspect ${k}`}>FLEX-{String(r?.flex_test_number).padStart(3, '0')}</button>;
                  })}
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="card" aria-labelledby="q-miss">
        <header className="card-head">
          <span className="eyebrow">Missingness · all {dataset.records.length} records</span>
          <h3 id="q-miss">Usable vs missing / invalid / approximate values by field and fuel</h3>
        </header>
        <div className="table-scroll"><table className="data">
          <thead><tr><th scope="col">Field</th>{FUELS.map((f) => <th scope="col" key={f}>{f}: usable / total</th>)}<th scope="col">Flags (count)</th></tr></thead>
          <tbody>{(NUMERIC_FIELDS as readonly NumericField[]).map((field) => {
            const flags: Record<string, number> = {};
            dataset.records.forEach((r) => (r.field_flags[field] ?? []).forEach((fl) => { flags[fl] = (flags[fl] ?? 0) + 1; }));
            return (
              <tr key={field}><th scope="row">{FIELD_LABEL[field]} ({dataset.units[field]})</th>
                {FUELS.map((f) => {
                  const rs = dataset.records.filter((r) => r.fuel === f);
                  return <td key={f} className="num">{rs.filter((r) => r.usable[field]).length} / {rs.length}</td>;
                })}
                <td>{Object.entries(flags).map(([k, n]) => `${k} (${n})`).join(', ') || '—'}</td></tr>
            );
          })}
            <tr><th scope="row">H₂O mole fraction</th><td className="unknown" colSpan={2}>UNKNOWN for all records (not in Table IX or PSI-69)</td><td>—</td></tr>
            <tr><th scope="row">Fuel-vapour mole fraction</th><td className="unknown" colSpan={2}>UNKNOWN for all records</td><td>—</td></tr>
          </tbody>
        </table></div>
      </section>

      <section className="card" aria-labelledby="q-rules">
        <header className="card-head">
          <span className="eyebrow">Documented rules · {dataset.provenance.audit_doc}</span>
          <h3 id="q-rules">Eligibility, quality and evidence rules</h3>
        </header>
        <dl className="rules">
          {Object.entries(dataset.rules).map(([id, text]) => (
            <div key={id} id={ruleAnchor(id)} className={focusRule === id ? 'rule focus' : 'rule'} tabIndex={-1}>
              <dt><code>{id}</code></dt><dd>{text}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

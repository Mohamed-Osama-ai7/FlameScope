import type { FlexRecord, NumericField } from '../data/types';
import { FIELD_LABEL, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';

/** Compact accessible table of records with an Inspect action (non-hover alternative to charts). */
export function RecordList({ records, fields }: { records: FlexRecord[]; fields: NumericField[] }) {
  const { select, selectedKey, dataset } = useLab();
  if (!records.length) return <p className="muted">No records.</p>;
  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th scope="col">FLEX</th><th scope="col">Identifier</th><th scope="col">Fuel</th><th scope="col">Support</th>
            {fields.map((f) => <th scope="col" key={f}>{FIELD_LABEL[f]} ({dataset.units[f]})</th>)}
            <th scope="col">Test end</th><th scope="col"><span className="sr-only">Action</span></th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.record_key} aria-selected={r.record_key === selectedKey} className={r.record_key === selectedKey ? 'is-selected' : undefined}>
              <td>FLEX-{String(r.flex_test_number).padStart(3, '0')}</td><td>{r.identifier}</td><td>{r.fuel}</td>
              <td>{SUPPORT_LABEL[r.support_mode]}</td>
              {fields.map((f) => <td key={f} className="num">{r.values[f] ?? 'missing'}</td>)}
              <td>{r.test_end}</td>
              <td><button type="button" className="link" onClick={() => select(r.record_key)} aria-label={`Inspect ${r.record_key}`}>Inspect</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useMemo } from 'react';
import { ChartCard } from '../components/ChartCard';
import { RecordList } from '../components/RecordList';
import { StrataTable } from '../components/StrataTable';
import { dextClassLabel, scatterFigure } from '../charts/specs';
import { applyFilters, DEXT_CLASS, strataFor, viewData, VIEWS } from '../data/selectors';
import { FUELS } from '../data/types';
import { useLab } from '../state/LabContext';
import { useNarrow } from '../state/useNarrow';

export function Outcomes() {
  const { dataset, filters, chartTheme, selectedKey } = useLab();
  const narrow = useNarrow();
  const vdOut = useMemo(() => viewData(dataset.records, VIEWS.outcome_o2_d0, filters), [dataset, filters]);
  const vdDext = useMemo(() => viewData(dataset.records, VIEWS.dext_o2, filters), [dataset, filters]);
  const figOut = useMemo(() => scatterFigure(dataset, vdOut, chartTheme, selectedKey, narrow), [dataset, vdOut, chartTheme, selectedKey, narrow]);
  const figDext = useMemo(() => scatterFigure(dataset, vdDext, chartTheme, selectedKey, narrow), [dataset, vdDext, chartTheme, selectedKey, narrow]);
  const { included } = useMemo(() => applyFilters(dataset.records, filters), [dataset, filters]);
  const extrapolated = included.filter((r) => r.dext_origin === 'reported_extinction_extrapolation_noted_in_caption');
  const origins = Object.keys(DEXT_CLASS).filter((o) => dataset.records.some((r) => r.dext_origin === o));

  return (
    <div className="stack">
      <section className="card" aria-labelledby="dext-sem">
        <header className="card-head">
          <span className="eyebrow">NASA outcome semantics · App. A.1</span>
          <h3 id="dext-sem">Extinction-diameter origin by fuel (records after visual filters)</h3>
          <p className="question">A missing extinction diameter has several distinct meanings; they are never merged.</p>
        </header>
        <div className="table-scroll"><table className="data" data-testid="dext-origin-table">
          <thead><tr><th scope="col">Origin (per NASA definitions and captions)</th>{FUELS.map((f) => <th scope="col" key={f}>{f}</th>)}<th scope="col">Rule</th></tr></thead>
          <tbody>{origins.map((o) => (
            <tr key={o}><th scope="row">{dextClassLabel(o)}</th>
              {FUELS.map((f) => <td className="num" key={f}>{included.filter((r) => r.fuel === f && r.dext_origin === o).length}</td>)}
              <td className="small"><code>{o}</code></td></tr>
          ))}</tbody>
        </table></div>
      </section>
      <div className="callout warn" role="note">
        <b>Contamination caveat (NASA/TP-2015-216046 §5.2).</b> {dataset.outcome_caveats.Methanol} {dataset.outcome_caveats.Heptane}
      </div>
      <ChartCard vd={vdOut} figure={figOut} />
      <ChartCard vd={vdDext} figure={figDext}>
        <StrataTable strata={strataFor(dataset, 'A6', filters.supportModes, filters.fuels)} caption={`v${dataset.analysis_version} A6 strata`} />
        <details className="table-alt">
          <summary>Extrapolated extinction diameters (NASA caption notes extrapolation; not in A6): {extrapolated.length}</summary>
          <RecordList records={extrapolated} fields={['ambient_oxygen_mole_fraction', 'initial_droplet_diameter', 'extinction_diameter']} />
        </details>
      </ChartCard>
    </div>
  );
}

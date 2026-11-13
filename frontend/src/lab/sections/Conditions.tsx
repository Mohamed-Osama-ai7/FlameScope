import { useMemo } from 'react';
import { ChartCard } from '../components/ChartCard';
import { Plot } from '../components/Plot';
import { coverageHeatmap, distributionFigure, scatterFigure } from '../charts/specs';
import { applyFilters, viewData, VIEWS } from '../data/selectors';
import { FAMILY_LABEL, FUELS } from '../data/types';
import { useLab } from '../state/LabContext';
import { useNarrow } from '../state/useNarrow';

export function Conditions() {
  const { dataset, filters, chartTheme, selectedKey } = useLab();
  const narrow = useNarrow();
  const vdPO2 = useMemo(() => viewData(dataset.records, VIEWS.cond_p_o2, filters), [dataset, filters]);
  const vdD0 = useMemo(() => viewData(dataset.records, VIEWS.cond_d0, filters), [dataset, filters]);
  const figPO2 = useMemo(() => scatterFigure(dataset, vdPO2, chartTheme, selectedKey, narrow), [dataset, vdPO2, chartTheme, selectedKey, narrow]);
  const figD0 = useMemo(() => distributionFigure(dataset, vdD0, chartTheme, 'box', selectedKey), [dataset, vdD0, chartTheme, selectedKey]);
  const { included } = useMemo(() => applyFilters(dataset.records, filters), [dataset, filters]);

  const compositions = useMemo(() => {
    const m = new Map<string, { fuel: string; o2: number | null; n2: number | null; co2: number | null; he: number | null; sum: number | null; cluster: string; fam: string; n: number }>();
    for (const r of included) {
      const v = r.values;
      const key = [r.fuel, v.ambient_oxygen_mole_fraction, v.ambient_nitrogen_mole_fraction, v.co2_mole_fraction, v.ambient_helium_mole_fraction, r.pressure_cluster].join('|');
      const row = m.get(key) ?? { fuel: r.fuel, o2: v.ambient_oxygen_mole_fraction, n2: v.ambient_nitrogen_mole_fraction, co2: v.co2_mole_fraction,
        he: v.ambient_helium_mole_fraction, sum: r.composition_sum, cluster: r.pressure_cluster ?? 'invalid pressure', fam: r.diluent_family, n: 0 };
      row.n += 1;
      m.set(key, row);
    }
    return [...m.values()].sort((a, b) => a.fuel.localeCompare(b.fuel) || (a.o2 ?? 0) - (b.o2 ?? 0) || (a.co2 ?? 0) - (b.co2 ?? 0) || (a.he ?? 0) - (b.he ?? 0));
  }, [included]);

  return (
    <div className="stack">
      <div className="callout" role="note">
        <b>Incomplete composition.</b> NASA App. A.1 defines H₂O and fuel-vapour mole fractions, but they are absent from Table IX and PSI-69.
        The recorded O₂/N₂/CO₂/He fractions are shown exactly as reported: they are never normalised to 100 % and no ternary plot is drawn.
      </div>
      <ChartCard vd={vdPO2} figure={figPO2} />
      <section className="card" aria-labelledby="cov-title">
        <header className="card-head">
          <span className="eyebrow">Coverage · counts only</span>
          <h3 id="cov-title">Experimental coverage and gaps (records after visual filters)</h3>
          <p className="question">Where were tests run? Empty cells (0) are untested combinations, not zero results.</p>
        </header>
        <div className="two-col">
          {FUELS.filter((f) => filters.fuels.includes(f)).map((f) => {
            const fig = coverageHeatmap(included, chartTheme, f);
            return <Plot key={f} data={fig.data} layout={fig.layout} label={`${f} coverage heatmap: record counts per diluent family and pressure cluster`} />;
          })}
        </div>
      </section>
      <ChartCard vd={vdD0} figure={figD0} />
      <section className="card" aria-labelledby="comp-title">
        <header className="card-head">
          <span className="eyebrow">Recorded composition vectors</span>
          <h3 id="comp-title">Distinct recorded atmospheres ({compositions.length})</h3>
        </header>
        <div className="table-scroll"><table className="data">
          <thead><tr><th scope="col">Fuel</th><th scope="col">Family</th><th scope="col">Pressure cluster</th><th scope="col">O₂</th><th scope="col">N₂</th><th scope="col">CO₂</th><th scope="col">He</th>
            <th scope="col">Recorded sum</th><th scope="col">H₂O</th><th scope="col">Fuel vapour</th><th scope="col">Records</th></tr></thead>
          <tbody>{compositions.map((c, i) => (
            <tr key={i}><td>{c.fuel}</td><td>{FAMILY_LABEL[c.fam as keyof typeof FAMILY_LABEL]}</td><td>{c.cluster.replace(' nominal', '')}</td>
              <td className="num">{c.o2}</td><td className="num">{c.n2}</td><td className="num">{c.co2}</td><td className="num">{c.he}</td>
              <td className="num">{c.sum}</td><td className="unknown">UNKNOWN</td><td className="unknown">UNKNOWN</td><td className="num">{c.n}</td></tr>
          ))}</tbody>
        </table></div>
      </section>
    </div>
  );
}

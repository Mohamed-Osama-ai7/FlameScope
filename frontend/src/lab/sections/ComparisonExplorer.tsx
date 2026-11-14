import { useEffect, useMemo, useState } from 'react';
import type { Data, Layout } from 'plotly.js';
import { api } from '../../api/client';
import type { ComparisonCondition, ComparisonResult, ObservationDescriptor } from '../../api/contracts';
import { Plot } from '../components/Plot';
import type { FlexRecord, LabDataset } from '../data/types';
import { useLab } from '../state/LabContext';

const CONDITION_FIELDS = [
  ['ambient_pressure', 'mmHg'],
  ['ambient_oxygen_mole_fraction', 'mole_fraction'],
  ['ambient_nitrogen_mole_fraction', 'mole_fraction'],
  ['ambient_helium_mole_fraction', 'mole_fraction'],
  ['co2_mole_fraction', 'mole_fraction'],
] as const;

function descriptorFor(record: FlexRecord): ObservationDescriptor {
  const conditions: Record<string, ComparisonCondition> = {};
  for (const [field, unit] of CONDITION_FIELDS) {
    const value = record.values[field];
    if (record.usable[field] && value !== null) conditions[field] = { value, unit };
  }
  return {
    investigation_id: 'PSI-69',
    regime: 'flex_droplet',
    variable: 'burning_rate_constant_mm2_s',
    unit: 'mm^2/s',
    material_or_fuel: record.fuel,
    conditions,
  };
}

function runLabel(record: FlexRecord): string {
  return `FLEX-${String(record.flex_test_number).padStart(3, '0')} · ${record.fuel} · ${record.identifier}`;
}

function ComparisonOutcome({ result }: { result: ComparisonResult }) {
  const canPlotTogether = result.shared_axis_allowed;
  return (
    <section className={`comparison-outcome ${canPlotTogether ? 'is-comparable' : 'is-contextual'}`} aria-live="polite" aria-labelledby="comparison-result-title">
      <div className="comparison-verdict">
        <span className="explorer-label">Comparison engine decision</span>
        <h3 id="comparison-result-title">{result.classification.replaceAll('_', ' ')}</h3>
        <strong>{canPlotTogether ? 'Shared quantitative axis allowed' : 'Keep runs off a shared quantitative axis'}</strong>
      </div>
      <div className="comparison-explanation">
        {result.reasons.length > 0 && <><h4>Why this decision</h4><ul>{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></>}
        {result.reasons.length === 0 && <p>The engine found matching recorded descriptors for these runs.</p>}
        <ComparisonDimensions title="Held constant" values={result.held_constant} />
        <ComparisonDimensions title="Different" values={result.differing} />
        <ComparisonDimensions title="Unknown or missing" values={result.unknown} />
      </div>
    </section>
  );
}

function ComparisonDimensions({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) return null;
  return <p className="small"><strong>{title}:</strong> {values.join(', ')}</p>;
}

export function ComparisonExplorer({ dataset }: { dataset: LabDataset }) {
  const { chartTheme, select } = useLab();
  const comparableRecords = useMemo(() => dataset.records.filter((record) =>
    record.usable.burning_rate_constant_mm2_s && record.values.burning_rate_constant_mm2_s !== null), [dataset.records]);
  const [firstKey, setFirstKey] = useState(comparableRecords[0]?.record_key ?? '');
  const [secondKey, setSecondKey] = useState(comparableRecords[1]?.record_key ?? '');
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [validatedSelection, setValidatedSelection] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const firstRecord = comparableRecords.find((record) => record.record_key === firstKey);
  const secondRecord = comparableRecords.find((record) => record.record_key === secondKey);
  const validatedPair = comparison?.shared_axis_allowed && validatedSelection === `${firstKey}|${secondKey}` && !loading && !error && firstRecord && secondRecord && firstKey !== secondKey
    ? { first: firstRecord, second: secondRecord }
    : null;
  const comparisonFigure = useMemo(() => {
    if (!validatedPair) return null;
    const data: Data[] = [{
      type: 'scatter', mode: 'markers', name: 'Validated FLEX runs',
      x: ['Run A', 'Run B'],
      y: [validatedPair.first.values.burning_rate_constant_mm2_s, validatedPair.second.values.burning_rate_constant_mm2_s],
      customdata: [validatedPair.first.record_key, validatedPair.second.record_key] as never,
      text: [runLabel(validatedPair.first), runLabel(validatedPair.second)],
      hovertemplate: '%{text}<br>Reported K: %{y} mm²/s<extra></extra>',
      marker: { color: chartTheme.series[0], size: 12, line: { color: chartTheme.bg, width: 2 } },
    } as Data];
    const layout: Partial<Layout> = {
      paper_bgcolor: chartTheme.bg, plot_bgcolor: chartTheme.bg,
      font: { family: chartTheme.font, color: chartTheme.fg },
      margin: { l: 70, r: 20, t: 30, b: 60 }, height: 360,
      xaxis: { title: { text: 'Validated run' }, type: 'category', gridcolor: chartTheme.grid, linecolor: chartTheme.axis },
      yaxis: { title: { text: `Reported burning-rate constant K (${dataset.units.burning_rate_constant_mm2_s})` }, gridcolor: chartTheme.grid, linecolor: chartTheme.axis, zeroline: false },
      hoverlabel: { bgcolor: chartTheme.bg, bordercolor: chartTheme.axis, font: { color: chartTheme.fg } },
      showlegend: false,
    };
    return { data, layout };
  }, [validatedPair, chartTheme, dataset.units.burning_rate_constant_mm2_s]);

  useEffect(() => {
    if (!firstRecord || !secondRecord || firstKey === secondKey) {
      setComparison(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setValidatedSelection('');
    api.validateComparison({ a: descriptorFor(firstRecord), b: descriptorFor(secondRecord) }, controller.signal)
      .then((result) => { setComparison(result); setValidatedSelection(`${firstKey}|${secondKey}`); })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) setError(requestError instanceof Error ? requestError.message : 'The comparison request failed.');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [firstKey, secondKey, firstRecord, secondRecord, retryKey]);

  return (
    <section className="card comparison-explorer" aria-labelledby="comparison-title">
      <div className="explorer-heading"><div><h3 id="comparison-title">Compare two FLEX runs</h3><p className="small muted">The comparison engine checks source-reported K and recorded conditions. Missing metadata stays unknown.</p></div><span className="explorer-status">PSI-69 · FLEX droplet</span></div>
      {comparableRecords.length < 2 ? <p className="explorer-state">At least two runs with usable reported burning-rate values are needed to compare.</p> : <>
        <div className="comparison-selectors">
          <label><span>Run A</span><select value={firstKey} onChange={(event) => setFirstKey(event.target.value)}>{comparableRecords.map((record) => <option key={record.record_key} value={record.record_key}>{runLabel(record)}</option>)}</select></label>
          <span className="comparison-operator" aria-hidden="true">vs</span>
          <label><span>Run B</span><select value={secondKey} onChange={(event) => setSecondKey(event.target.value)}>{comparableRecords.map((record) => <option key={record.record_key} value={record.record_key}>{runLabel(record)}</option>)}</select></label>
        </div>
        {firstKey === secondKey && <p className="explorer-state" role="status">Choose two different runs to request a comparison.</p>}
        {firstRecord && secondRecord && <div className="comparison-pair" aria-label="Selected run details">
        {[{ label: 'Run A', record: firstRecord }, { label: 'Run B', record: secondRecord }].map(({ label, record }) => <div key={label}><span className="explorer-label">{label}</span><strong>{runLabel(record)}</strong><span className="small muted">K = {record.values.burning_rate_constant_mm2_s} mm²/s · {record.diluent_family.replaceAll('_', ' ')}</span></div>)}
        </div>}
        {loading && <p className="explorer-state" role="status">Checking the scientific comparison rules…</p>}
        {error && <div className="explorer-error" role="alert"><p><strong>Comparison could not be validated.</strong> {error}</p><button type="button" onClick={() => setRetryKey((key) => key + 1)}>Retry comparison</button></div>}
        {!loading && !error && comparison && <ComparisonOutcome result={comparison} />}
        {validatedPair && comparisonFigure && <section className="comparison-plot" aria-labelledby="validated-plot-title">
          <h4 id="validated-plot-title">Reported K for this validated pair</h4>
          <p className="small muted">Shared-axis display is enabled by the comparison engine result above. Values are NASA-reported; no uncertainty is supplied in this dataset. Select a point to inspect its source evidence.</p>
          <Plot data={comparisonFigure.data} layout={comparisonFigure.layout} label={`Validated comparison of reported K: Run A ${validatedPair.first.values.burning_rate_constant_mm2_s} and Run B ${validatedPair.second.values.burning_rate_constant_mm2_s} ${dataset.units.burning_rate_constant_mm2_s}.`} onSelect={(key) => select(key)} />
          <details className="table-alt"><summary>Validated comparison values as a table</summary>
            <div className="table-scroll"><table className="data"><thead><tr><th scope="col">Run</th><th scope="col">Fuel</th><th scope="col">Reported K ({dataset.units.burning_rate_constant_mm2_s})</th><th scope="col">Source record</th><th scope="col">Evidence</th></tr></thead>
              <tbody>{[{ label: 'Run A', record: validatedPair.first }, { label: 'Run B', record: validatedPair.second }].map(({ label, record }) => <tr key={label}>
                <th scope="row">{label}</th><td>{record.fuel}</td><td className="num">{record.values.burning_rate_constant_mm2_s}</td><td>FLEX-{String(record.flex_test_number).padStart(3, '0')} · {record.identifier}</td><td><button type="button" className="link" onClick={() => select(record.record_key)}>Inspect evidence</button></td>
              </tr>)}</tbody>
            </table></div>
          </details>
        </section>}
      </>}
    </section>
  );
}

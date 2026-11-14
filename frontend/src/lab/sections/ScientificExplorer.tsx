import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { MethodCard, RegimeRecord, SourceRecord } from '../../api/contracts';
import type { FlexRecord, NumericField } from '../data/types';
import { countBy } from '../data/selectors';
import { useLab } from '../state/LabContext';

interface ResourceState<T> {
  items: T[];
  error: string | null;
}

interface ExplorerResources {
  sources: ResourceState<SourceRecord>;
  regimes: ResourceState<RegimeRecord>;
  methods: ResourceState<MethodCard>;
}

const EMPTY_RESOURCE = { items: [], error: null };

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'The API request failed.';
}

function formatNumber(value: number | null, unit: string): string {
  return value === null ? 'Not reported' : `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${unit}`;
}

function numericRange(records: FlexRecord[], field: NumericField, unit: string): string {
  const values = records.flatMap((record) => {
    const value = record.values[field];
    return record.usable[field] && value !== null ? [value] : [];
  });
  if (values.length === 0) return `No usable values (${unit})`;
  const low = Math.min(...values);
  const high = Math.max(...values);
  return low === high
    ? formatNumber(low, unit)
    : `${formatNumber(low, unit)} to ${formatNumber(high, unit)}`;
}

function LoadingList({ label }: { label: string }) {
  return (
    <div className="explorer-skeleton" role="status" aria-label={`Loading ${label}`}>
      <span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" />
    </div>
  );
}

function ResourceError({ label, message, onRetry }: { label: string; message: string; onRetry: () => void }) {
  return (
    <div className="explorer-error" role="alert">
      <p><strong>{label} could not be loaded.</strong> {message}</p>
      <button type="button" className="ghost" onClick={onRetry}>Retry all registry requests</button>
    </div>
  );
}

function SourcesList({ items }: { items: SourceRecord[] }) {
  if (!items.length) return <p className="explorer-state">No sources are registered in the API yet.</p>;
  return (
    <ul className="explorer-list">
      {items.map((source) => (
        <li key={source.source_id}>
          <div className="explorer-row-head">
            <strong>{source.source_title}</strong>
            <span className={`explorer-status status-${source.verification_status.toLowerCase()}`}>
              {source.verification_status.replaceAll('_', ' ')}
            </span>
          </div>
          <p className="explorer-meta"><span>{source.source_id}</span><span>{source.source_type}</span></p>
          {source.official_challenge_resource && <span className="source-flag">Official challenge resource</span>}
          {source.verification_status === 'RESOURCE_RECORDED' && (
            <p className="small muted">Catalogue entry, not a data file: never evidence on its own; its data enter only through registered child sources.</p>
          )}
          <div className="explorer-links">
            {source.doi && <span>DOI: {source.doi}</span>}
            {source.version_or_release && <span>{source.version_or_release}</span>}
            {source.license && <span>License: {source.license}</span>}
            {source.retrieved_at_utc && <span>Retrieved: {source.retrieved_at_utc}</span>}
            {source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">Open source ↗</a>}
          </div>
          {source.sha256 && <p className="explorer-meta">SHA-256: <code>{source.sha256.slice(0, 16)}…</code></p>}
          {source.notes && <p className="small muted">{source.notes}</p>}
        </li>
      ))}
    </ul>
  );
}

function RegimesList({ items }: { items: RegimeRecord[] }) {
  if (!items.length) return <p className="explorer-state">No combustion regimes are available.</p>;
  return (
    <ul className="explorer-list">
      {items.map((regime) => (
        <li key={regime.regime}>
          <strong>{regime.regime.replaceAll('_', ' ')}</strong>
          <p className="small muted">{regime.description}</p>
          <p className="explorer-label">Controlled variables</p>
          <div className="explorer-chips">
            {regime.variables.map((variable) => <span className="explorer-chip" key={variable}>{variable}</span>)}
          </div>
        </li>
      ))}
    </ul>
  );
}

function MethodsList({ items }: { items: MethodCard[] }) {
  if (!items.length) return <p className="explorer-state">No analysis methods are registered.</p>;
  return (
    <ul className="explorer-list">
      {items.map((method) => (
        <li key={method.method_id}>
          <div className="explorer-row-head">
            <strong>{method.title}</strong>
            <span className="explorer-status">{method.status.replaceAll('_', ' ')}</span>
          </div>
          <p className="explorer-meta"><span>{method.method_id}</span><span>v{method.version}</span></p>
          <div className="explorer-chips">
            {method.regimes.map((regime) => <span className="explorer-chip" key={regime}>{regime.replaceAll('_', ' ')}</span>)}
          </div>
          <p className="formula"><code>{method.formula}</code></p>
          <details>
            <summary>Method assumptions and limits</summary>
            <p><strong>Variables</strong></p>
            <ul>{method.variables.map((variable) => <li key={`${variable.symbol}-${variable.role}`}>{variable.symbol}: {variable.name} ({variable.role}, {variable.unit})</li>)}</ul>
            <p><strong>Assumptions</strong></p>
            <ul>{method.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
            <p><strong>Validity limits</strong></p>
            <ul>{method.validity_limits.map((limit) => <li key={limit}>{limit}</li>)}</ul>
            <p><strong>Required inputs</strong></p>
            <ul>{method.required_inputs.map((input) => <li key={input}>{input}</li>)}</ul>
            <p><strong>Uncertainty</strong></p>
            <p>{method.uncertainty_method}</p>
            <p><strong>Validation</strong></p>
            <ul>{method.validation.map((statement) => <li key={statement}>{statement}</li>)}</ul>
            <p><strong>Abstention conditions</strong></p>
            <ul>{method.abstention_conditions.map((condition) => <li key={condition}>{condition}</li>)}</ul>
            <p><strong>References</strong></p>
            <ul>{method.references.map((reference) => <li key={reference.citation}>{reference.citation}{reference.doi && <> · DOI <a href={`https://doi.org/${encodeURIComponent(reference.doi)}`} target="_blank" rel="noreferrer">{reference.doi}</a></>}</li>)}</ul>
          </details>
        </li>
      ))}
    </ul>
  );
}

function DatasetSummary({ dataset }: { dataset: ReturnType<typeof useLab>['dataset'] }) {
  const fuelCounts = useMemo(() => countBy(dataset.records, (record) => record.fuel), [dataset.records]);
  const familyCounts = useMemo(() => countBy(dataset.records, (record) => record.diluent_family), [dataset.records]);
  const oxygenUnit = dataset.units.ambient_oxygen_mole_fraction;
  const pressureUnit = dataset.units.ambient_pressure;
  const burningRateUnit = dataset.units.burning_rate_constant_mm2_s;
  return (
    <section className="card dataset-summary" aria-labelledby="dataset-title">
      <div className="explorer-heading"><div><h3 id="dataset-title">Dataset and conditions</h3><p className="small muted">{dataset.dataset} · dataset v{dataset.dataset_version} · analysis v{dataset.analysis_version}</p></div><span className="explorer-status">{dataset.scope.records} records</span></div>
      <p className="small">Source: {dataset.provenance.source_id} · DOI {dataset.provenance.doi}</p>
      <div className="condition-grid">
        <div><span className="explorer-label">Fuels represented</span><p>{Object.entries(fuelCounts).map(([fuel, count]) => `${fuel} (${count})`).join(' · ')}</p></div>
        <div><span className="explorer-label">Recorded diluent families</span><p>{Object.entries(familyCounts).map(([family, count]) => `${family.replaceAll('_', ' ')} (${count})`).join(' · ')}</p></div>
        <div><span className="explorer-label">Ambient oxygen range</span><p>{numericRange(dataset.records, 'ambient_oxygen_mole_fraction', oxygenUnit)}</p></div>
        <div><span className="explorer-label">Ambient pressure range</span><p>{numericRange(dataset.records, 'ambient_pressure', pressureUnit)}</p></div>
        <div><span className="explorer-label">Reported burning-rate range</span><p>{numericRange(dataset.records, 'burning_rate_constant_mm2_s', burningRateUnit)}</p></div>
      </div>
      <p className="small muted">Ranges include only records marked usable for each field. They describe this dataset and do not imply that records from different regimes are comparable.</p>
    </section>
  );
}

function ExperimentRecords({ dataset, onSelect }: { dataset: ReturnType<typeof useLab>['dataset']; onSelect: (key: string) => void }) {
  const [query, setQuery] = useState('');
  const records = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return dataset.records;
    return dataset.records.filter((record) => [record.record_key, record.identifier, String(record.flex_test_number), record.fuel, record.test_date]
      .some((field) => field.toLowerCase().includes(term)));
  }, [dataset.records, query]);
  const oxygenUnit = dataset.units.ambient_oxygen_mole_fraction;
  const pressureUnit = dataset.units.ambient_pressure;
  const burningRateUnit = dataset.units.burning_rate_constant_mm2_s;
  return (
    <section className="card run-explorer" aria-labelledby="run-title">
      <div className="explorer-heading"><div><h3 id="run-title">FLEX experiment records</h3><p className="small muted">Search test numbers, identifiers, fuel, or date. Select a test number to open its evidence inspector.</p></div><span className="explorer-status">{records.length} matches</span></div>
      <label className="explorer-search"><span>Find an experiment</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Test number, identifier, fuel, or date" /></label>
      {records.length === 0 ? <p className="explorer-state">No FLEX records match “{query}”. Try a test number, fuel, or date.</p> : <ExperimentTable records={records} onSelect={onSelect} oxygenUnit={oxygenUnit} pressureUnit={pressureUnit} burningRateUnit={burningRateUnit} />}
    </section>
  );
}

function ExperimentTable({ records, onSelect, oxygenUnit, pressureUnit, burningRateUnit }: {
  records: FlexRecord[];
  onSelect: (key: string) => void;
  oxygenUnit: string;
  pressureUnit: string;
  burningRateUnit: string;
}) {
  return (
    <div className="table-scroll">
      <p className="explorer-table-hint small muted">Scroll horizontally to see all condition columns.</p>
      <table className="data explorer-record-table">
        <thead><tr><th scope="col">Test</th><th scope="col">Fuel</th><th scope="col">Date</th><th scope="col">O₂ mole fraction</th><th scope="col">Pressure</th><th scope="col">Reported K</th></tr></thead>
        <tbody>{records.slice(0, 12).map((record) => (
          <tr key={record.record_key}>
            <th scope="row"><button type="button" className="link" onClick={() => onSelect(record.record_key)}>FLEX-{String(record.flex_test_number).padStart(3, '0')}</button><span className="explorer-record-id">{record.identifier}</span></th>
            <td>{record.fuel}</td><td>{record.test_date}</td>
            <td>{formatNumber(record.usable.ambient_oxygen_mole_fraction ? record.values.ambient_oxygen_mole_fraction : null, oxygenUnit)}</td>
            <td>{formatNumber(record.usable.ambient_pressure ? record.values.ambient_pressure : null, pressureUnit)}</td>
            <td>{formatNumber(record.usable.burning_rate_constant_mm2_s ? record.values.burning_rate_constant_mm2_s : null, burningRateUnit)}</td>
          </tr>
        ))}</tbody>
      </table>
      {records.length > 12 && <p className="small muted">Showing the first 12 records. Narrow the search to find a specific test.</p>}
    </div>
  );
}

function RegistryPanels({ resources, loading, onRetry }: { resources: ExplorerResources; loading: boolean; onRetry: () => void }) {
  return (
    <section className="api-explorer" aria-label="Scientific registry">
      <section className="card api-column" aria-labelledby="sources-title"><h3 id="sources-title">Sources</h3>{loading ? <LoadingList label="sources" /> : resources.sources.error ? <ResourceError label="Sources" message={resources.sources.error} onRetry={onRetry} /> : <SourcesList items={resources.sources.items} />}</section>
      <section className="card api-column" aria-labelledby="regimes-title"><h3 id="regimes-title">Combustion regimes</h3>{loading ? <LoadingList label="regimes" /> : resources.regimes.error ? <ResourceError label="Regimes" message={resources.regimes.error} onRetry={onRetry} /> : <RegimesList items={resources.regimes.items} />}</section>
      <section className="card api-column" aria-labelledby="methods-title"><h3 id="methods-title">Analysis methods</h3>{loading ? <LoadingList label="methods" /> : resources.methods.error ? <ResourceError label="Methods" message={resources.methods.error} onRetry={onRetry} /> : <MethodsList items={resources.methods.items} />}</section>
    </section>
  );
}

export function ScientificExplorer() {
  const { dataset, select } = useLab();
  const [resources, setResources] = useState<ExplorerResources>({ sources: EMPTY_RESOURCE, regimes: EMPTY_RESOURCE, methods: EMPTY_RESOURCE });
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      api.listSources().then((items) => ({ items, error: null })).catch((error: unknown) => ({ items: [], error: errorText(error) })),
      api.listRegimes().then((items) => ({ items, error: null })).catch((error: unknown) => ({ items: [], error: errorText(error) })),
      api.listMethods().then((items) => ({ items, error: null })).catch((error: unknown) => ({ items: [], error: errorText(error) })),
    ]).then(([sources, regimes, methods]) => {
      if (active) { setResources({ sources, regimes, methods }); setLoading(false); }
    });
    return () => { active = false; };
  }, [reloadKey]);
  const retry = () => setReloadKey((key) => key + 1);
  return (
    <div className="explorer-page">
      <section className="explorer-intro"><h2>Scientific Explorer</h2><p>Browse the source registry and scientific vocabulary, then inspect individual FLEX test records with their reported conditions and evidence.</p><p className="small muted">Registry metadata comes from the API. Experimental records below come from the verified FLEX dataset shown in the lab.</p></section>
      <DatasetSummary dataset={dataset} />
      <ExperimentRecords dataset={dataset} onSelect={select} />
      <RegistryPanels resources={resources} loading={loading} onRetry={retry} />
    </div>
  );
}

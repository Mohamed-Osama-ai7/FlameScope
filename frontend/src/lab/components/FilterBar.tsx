import { useMemo } from 'react';
import type { Filters } from '../data/selectors';
import { allOptions, applyFilters, PRESSURE_INVALID } from '../data/selectors';
import { FAMILY_LABEL, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';

type ListKey = 'fuels' | 'supportModes' | 'families' | 'clusters' | 'testEnds';

const LABELS: Record<ListKey, string> = {
  fuels: 'Fuel', supportModes: 'Support mode', families: 'Diluent family', clusters: 'Pressure cluster', testEnds: 'Test end',
};

function display(key: ListKey, v: string): string {
  if (key === 'supportModes') return SUPPORT_LABEL[v as keyof typeof SUPPORT_LABEL] ?? v;
  if (key === 'families') return FAMILY_LABEL[v as keyof typeof FAMILY_LABEL] ?? v;
  if (key === 'clusters') return v === PRESSURE_INVALID ? 'Invalid pressure' : v.replace(' nominal', '');
  return v;
}

export function FilterBar() {
  const { dataset, filters, setFilters, resetFilters } = useLab();
  const options = useMemo(() => allOptions(dataset.records), [dataset]);
  const { included, excludedByFilter } = useMemo(() => applyFilters(dataset.records, filters), [dataset, filters]);

  const toggle = (key: ListKey, value: string) => {
    const list = filters[key] as string[];
    const next = list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
    setFilters({ ...filters, [key]: next } as Filters);
  };

  return (
    <aside className="filters card" aria-labelledby="filters-title">
      <div className="filters-head">
        <h2 id="filters-title" className="eyebrow">Visual filters</h2>
        <button type="button" className="ghost" onClick={resetFilters}>Reset filters</button>
      </div>
      <p className="muted small">
        Visual filters only hide records. Scientific eligibility rules are fixed per chart and listed on each chart.
        Support modes are never pooled: each selected mode gets its own panels.
      </p>
      {(Object.keys(LABELS) as ListKey[]).map((key) => (
        <fieldset key={key}>
          <legend>{LABELS[key]}</legend>
          {(options[key] as string[]).map((v) => {
            const id = `f-${key}-${v}`.replace(/[^a-zA-Z0-9-]/g, '_');
            return (
              <label key={v} htmlFor={id} className="check">
                <input id={id} type="checkbox" checked={(filters[key] as string[]).includes(v)} onChange={() => toggle(key, v)} />
                <span>{display(key, v)}</span>
                <span className="count">{dataset.records.filter((r) => (key === 'fuels' ? r.fuel : key === 'supportModes' ? r.support_mode : key === 'families' ? r.diluent_family : key === 'clusters' ? (r.pressure_cluster ?? PRESSURE_INVALID) : r.test_end) === v).length}</span>
              </label>
            );
          })}
        </fieldset>
      ))}
      <fieldset>
        <legend>Sensitivity rows</legend>
        <label htmlFor="f-sens" className="check">
          <input id="f-sens" type="checkbox" checked={filters.hideSensitivityRows} onChange={() => setFilters({ ...filters, hideSensitivityRows: !filters.hideSensitivityRows })} />
          <span>Hide FLEX-001…009 (1/30 s shutter) and FLEX-130 (visual only; primary results keep them)</span>
        </label>
      </fieldset>
      <div className="filter-summary" role="status" aria-live="polite" data-testid="filter-summary">
        <b>{included.length}</b> of {dataset.records.length} records pass the visual filters
        {Object.keys(excludedByFilter).length > 0 && (
          <> · hidden by {Object.entries(excludedByFilter).map(([k, n]) => `${k} (${n})`).join(', ')}</>
        )}
      </div>
    </aside>
  );
}

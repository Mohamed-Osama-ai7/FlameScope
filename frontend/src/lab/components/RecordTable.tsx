import {
  createColumnHelper, flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import { useEffect, useMemo, useRef, useState } from 'react';
import { dextClassLabel } from '../charts/specs';
import { downloadText, recordsToCsv } from '../data/export';
import { applyFilters } from '../data/selectors';
import type { FlexRecord } from '../data/types';
import { FAMILY_LABEL, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';

const col = createColumnHelper<FlexRecord>();

export function RecordTable() {
  const { dataset, filters, select, selectedKey } = useLab();
  const { included } = useMemo(() => applyFilters(dataset.records, filters), [dataset, filters]);
  const [sorting, setSorting] = useState<SortingState>([{ id: 'flex', desc: false }]);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const selectedRow = useRef<HTMLTableRowElement | null>(null);

  const columns = useMemo(() => [
    col.accessor((r) => r.flex_test_number, { id: 'flex', header: 'FLEX', cell: (c) => `FLEX-${String(c.getValue()).padStart(3, '0')}` }),
    col.accessor('psi_row', { header: 'PSI row' }),
    col.accessor('identifier', { header: 'Identifier' }),
    col.accessor('fuel', { header: 'Fuel' }),
    col.accessor((r) => SUPPORT_LABEL[r.support_mode], { id: 'support', header: 'Support mode' }),
    col.accessor((r) => FAMILY_LABEL[r.diluent_family], { id: 'family', header: 'Diluent' }),
    col.accessor((r) => r.values.ambient_pressure, { id: 'p', header: 'P (mmHg)' }),
    col.accessor((r) => r.values.ambient_oxygen_mole_fraction, { id: 'o2', header: 'O₂' }),
    col.accessor((r) => r.values.co2_mole_fraction, { id: 'co2', header: 'CO₂' }),
    col.accessor((r) => r.values.ambient_helium_mole_fraction, { id: 'he', header: 'He' }),
    col.accessor((r) => r.values.initial_droplet_diameter, { id: 'd0', header: 'D₀ (mm)' }),
    col.accessor((r) => r.values.burning_rate_constant_mm2_s, { id: 'k', header: 'Reported K (mm²/s)' }),
    col.accessor((r) => r.values.extinction_diameter, { id: 'dext', header: 'D_ext (mm)' }),
    col.accessor('test_end', { header: 'Test end' }),
    col.accessor((r) => dextClassLabel(r.dext_origin), { id: 'dorigin', header: 'D_ext origin' }),
    col.accessor((r) => [...r.row_flags, ...r.sensitivity_tags, ...Object.values(r.field_flags).flat()].join(', '), { id: 'flags', header: 'Flags' }),
  ], []);

  const table = useReactTable({
    data: included, columns, state: { sorting, globalFilter: query },
    onSortingChange: setSorting, onGlobalFilterChange: setQuery,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel(),
    getRowId: (r) => r.record_key,
  });
  const rows = table.getRowModel().rows;

  useEffect(() => {
    selectedRow.current?.scrollIntoView?.({ block: 'nearest' });
  }, [selectedKey]);

  return (
    <section className="card" aria-labelledby="obs-title">
      <header className="card-head">
        <span className="eyebrow">Observations explorer · TanStack Table</span>
        <h3 id="obs-title">Source records ({rows.length} shown of {included.length} after filters; {dataset.records.length} total)</h3>
        <p className="question">Every PSI-69 record with NASA-reported values. Empty cells mean missing in the source; see Flags.</p>
      </header>
      <div className="table-tools">
        <label htmlFor="obs-search">Search records</label>
        <input id="obs-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="identifier, fuel, flag…" />
        <button type="button" onClick={() => {
          const csv = recordsToCsv(dataset, rows.map((r) => r.original));
          downloadText(`flamescope_flex_observations_v${dataset.analysis_version}.csv`, csv, 'text/csv');
          setStatus(`CSV exported: ${rows.length} records (filtered raw observations, NASA-reported values).`);
        }}>Export CSV ({rows.length})</button>
        <span className="status" role="status" aria-live="polite">{status}</span>
      </div>
      <div className="table-scroll tall">
        <table className="data sticky" data-testid="record-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const s = h.column.getIsSorted();
                  return (
                    <th key={h.id} scope="col" aria-sort={s === 'asc' ? 'ascending' : s === 'desc' ? 'descending' : 'none'}>
                      <button type="button" className="sort" onClick={h.column.getToggleSortingHandler()}>
                        {flexRender(h.column.columnDef.header, h.getContext())}{s === 'asc' ? ' ▲' : s === 'desc' ? ' ▼' : ''}
                      </button>
                    </th>
                  );
                })}
                <th scope="col"><span className="sr-only">Inspect</span></th>
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map((row) => {
              const sel = row.id === selectedKey;
              return (
                <tr key={row.id} ref={sel ? selectedRow : undefined} className={sel ? 'is-selected' : undefined} aria-selected={sel} data-record-key={row.id}>
                  {row.getVisibleCells().map((c) => (
                    <td key={c.id} className={typeof c.getValue() === 'number' ? 'num' : undefined}>
                      {c.getValue() === null ? <span className="muted">—</span> : flexRender(c.column.columnDef.cell, c.getContext())}
                    </td>
                  ))}
                  <td><button type="button" className="link" onClick={() => select(row.id)} aria-label={`Inspect ${row.id}`}>Inspect</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

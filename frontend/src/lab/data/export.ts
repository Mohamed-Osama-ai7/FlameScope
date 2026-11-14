/** Export builders. Every export states its data type and carries provenance, filters and methodology. */
import type { Filters, ViewData } from './selectors';
import type { FlexRecord, LabDataset, NumericField } from './types';
import { NUMERIC_FIELDS } from './types';

export type ExportType =
  | 'filtered raw observations (NASA-reported values; no calculation)'
  | 'chart configuration (record keys and settings; no calculation)'
  | 'analysis summary (Python v0.2.0 strata statistics; aggregated)'
  | 'provenance metadata';

export class ExportError extends Error {}

function guard(d: LabDataset, allowSynthetic = false) {
  if (d.synthetic && !allowSynthetic) throw new ExportError('Synthetic data must never be exported as scientific output.');
}

export function provenanceBlock(d: LabDataset) {
  return {
    dataset: d.dataset,
    dataset_version: d.dataset_version,
    analysis_version: d.analysis_version,
    synthetic: d.synthetic,
    value_origin: d.value_origin,
    ...d.provenance,
  };
}

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return '';
  const s = Array.isArray(v) ? v.join(';') : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

export const CSV_COLUMNS = [
  'record_key', 'psi_row', 'flex_test_number', 'identifier', 'test_date', 'test_gmt', 'fuel', 'test_end',
  'support_mode', 'diluent_family', 'pressure_cluster', 'dext_origin',
  ...NUMERIC_FIELDS.flatMap((f) => [`${f}`, `${f}__raw`, `${f}__unit`, `${f}__flags`]),
  'row_flags', 'sensitivity_tags', 'eligible_analyses',
  'export_type', 'dataset_version', 'analysis_version', 'raw_sha256', 'enrichment_sha256', 'source_url',
] as const;

export function recordsToCsv(d: LabDataset, records: FlexRecord[], opts: { allowSynthetic?: boolean } = {}): string {
  guard(d, opts.allowSynthetic);
  const type: ExportType = 'filtered raw observations (NASA-reported values; no calculation)';
  const lines = [CSV_COLUMNS.join(',')];
  for (const r of records) {
    const row: Record<string, unknown> = {
      record_key: r.record_key, psi_row: r.psi_row, flex_test_number: r.flex_test_number, identifier: r.identifier,
      test_date: r.test_date, test_gmt: r.test_gmt, fuel: r.fuel, test_end: r.test_end, support_mode: r.support_mode,
      diluent_family: r.diluent_family, pressure_cluster: r.pressure_cluster, dext_origin: r.dext_origin,
      row_flags: r.row_flags, sensitivity_tags: r.sensitivity_tags, eligible_analyses: r.eligible,
      export_type: type, dataset_version: d.dataset_version, analysis_version: d.analysis_version,
      raw_sha256: d.provenance.raw_sha256, enrichment_sha256: d.provenance.enrichment_sha256,
      source_url: d.provenance.source_url,
    };
    for (const f of NUMERIC_FIELDS as readonly NumericField[]) {
      row[f] = r.values[f];
      row[`${f}__raw`] = r.raw[f];
      row[`${f}__unit`] = d.units[f];
      row[`${f}__flags`] = r.field_flags[f] ?? [];
    }
    lines.push(CSV_COLUMNS.map((c) => csvCell(row[c])).join(','));
  }
  return lines.join('\n') + '\n';
}

export function filtersJson(f: Filters) {
  return { ...f, note: 'Visual filters only; scientific eligibility is defined by the view rule.' };
}

export function chartConfig(d: LabDataset, vd: ViewData, f: Filters, opts: { allowSynthetic?: boolean } = {}) {
  guard(d, opts.allowSynthetic);
  return {
    export_type: 'chart configuration (record keys and settings; no calculation)' as ExportType,
    view: { id: vd.view.id, title: vd.view.title, question: vd.view.question, x: vd.view.x, y: vd.view.y,
      units: { x: vd.view.x ? d.units[vd.view.x] : null, y: d.units[vd.view.y] },
      eligibility_rule: vd.view.rule, analysis: vd.view.analysis, limitations: vd.view.limitations },
    filters: filtersJson(f),
    counts: { eligible: vd.eligible.length, shown: vd.shown.length, ineligible_by_reason: vd.ineligible,
      excluded_by_filter: vd.excludedByFilter },
    panels: vd.panels.map((p) => ({ fuel: p.fuel, support_mode: p.support, n: p.records.length,
      record_keys: p.records.map((r) => r.record_key) })),
    provenance: provenanceBlock(d),
  };
}

export function analysisSummary(d: LabDataset, f: Filters, opts: { allowSynthetic?: boolean } = {}) {
  guard(d, opts.allowSynthetic);
  return {
    export_type: 'analysis summary (Python v0.2.0 strata statistics; aggregated)' as ExportType,
    methodology: {
      statistic: 'Spearman rank correlation computed in Python (backend/app/analysis/flex_run_level.py); descriptive only, no p-values.',
      rules: d.rules,
      unknown_fields: d.unknown_fields,
      outcome_caveats: d.outcome_caveats,
    },
    filters_at_export: filtersJson(f),
    scope: d.scope,
    strata: d.strata,
    provenance: provenanceBlock(d),
  };
}

export function downloadText(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

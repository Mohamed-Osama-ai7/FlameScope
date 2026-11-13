import { useEffect, useRef } from 'react';
import { dextClassLabel } from '../charts/specs';
import type { NumericField } from '../data/types';
import { FAMILY_LABEL, FIELD_LABEL, NUMERIC_FIELDS, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';

/** Modal evidence inspector: every identifier, raw vs canonical value, flag, note, reference and hash. */
export function EvidenceInspector() {
  const { dataset, byKey, selectedKey, inspectorOpen, closeInspector } = useLab();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  const r = selectedKey ? byKey.get(selectedKey) : undefined;

  useEffect(() => {
    if (!inspectorOpen) return;
    opener.current = document.activeElement;
    panel.current?.querySelector<HTMLElement>('h2')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeInspector();
      if (e.key === 'Tab' && panel.current) {
        const f = panel.current.querySelectorAll<HTMLElement>('a[href],button,[tabindex="0"],summary');
        if (!f.length) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [inspectorOpen, closeInspector]);

  if (!inspectorOpen || !r) return null;
  const p = dataset.provenance;
  const ev = r.evidence;
  const reportPage = (page: number | null) => (page ? `${p.report_url}#page=${page}` : null);

  return (
    <div className="inspector-backdrop" onClick={closeInspector}>
      <div ref={panel} className="inspector" role="dialog" aria-modal="true" aria-labelledby="inspector-title" onClick={(e) => e.stopPropagation()} data-testid="inspector">
        <div className="inspector-head">
          <div>
            <span className="eyebrow">Evidence inspector · {r.fuel} · {SUPPORT_LABEL[r.support_mode]}</span>
            <h2 id="inspector-title" tabIndex={-1}>FLEX-{String(r.flex_test_number).padStart(3, '0')} · {r.identifier}</h2>
            <code className="key" data-testid="inspector-key">{r.record_key}</code>
          </div>
          <button type="button" className="ghost" onClick={closeInspector}>Close <span className="sr-only">inspector</span>(Esc)</button>
        </div>

        <section aria-labelledby="ins-ids"><h3 id="ins-ids">Identity</h3>
          <dl className="kv">
            <div><dt>PSI-69 row</dt><dd>{r.psi_row}</dd></div>
            <div><dt>NASA FLEX test</dt><dd>FLEX-{String(r.flex_test_number).padStart(3, '0')}</dd></div>
            <div><dt>FLEX identifier</dt><dd>{r.identifier}{r.row_flags.includes('duplicate_source_identifier') && <span className="tag warn">duplicate identifier in source</span>}</dd></div>
            <div><dt>Date · GMT</dt><dd>{r.test_date} · {r.test_gmt ?? 'missing in source'}</dd></div>
            <div><dt>Test end (NASA)</dt><dd>{r.test_end}</dd></div>
            <div><dt>Match method</dt><dd>{ev.match_method}</dd></div>
          </dl>
        </section>

        <section aria-labelledby="ins-vals"><h3 id="ins-vals">Values: original vs canonical</h3>
          <div className="table-scroll"><table className="data">
            <thead><tr><th scope="col">Canonical variable</th><th scope="col">Original PSI header</th><th scope="col">Raw</th><th scope="col">Canonical</th><th scope="col">Unit</th><th scope="col">Flags</th></tr></thead>
            <tbody>{(NUMERIC_FIELDS as readonly NumericField[]).map((f) => (
              <tr key={f}><th scope="row">{FIELD_LABEL[f]}</th><td><code>{dataset.raw_headers[f]}</code></td><td><code>{r.raw[f] === '' ? '(blank)' : r.raw[f]}</code></td>
                <td className="num">{r.values[f] ?? '—'}</td><td>{dataset.units[f]}</td><td>{(r.field_flags[f] ?? []).join(', ') || '—'}</td></tr>
            ))}</tbody>
          </table></div>
          <p className="small muted">K is the NASA-reported average burning-rate constant (NASA/TP-2015-216046 App. A.1); not a FlameScope calculation. Its uncertainty is UNKNOWN; ±50 µm is the droplet-size uncertainty.</p>
        </section>

        <section aria-labelledby="ins-cond"><h3 id="ins-cond">Conditions and classification</h3>
          <dl className="kv">
            <div><dt>Diluent family</dt><dd>{FAMILY_LABEL[r.diluent_family]}</dd></div>
            <div><dt>Recorded fraction sum</dt><dd>{r.composition_sum ?? '—'} (O₂+N₂+CO₂+He; H₂O and fuel vapour UNKNOWN; not normalised)</dd></div>
            <div><dt>Pressure cluster</dt><dd>{r.pressure_cluster ?? 'invalid pressure'}</dd></div>
            <div><dt>Support mode</dt><dd>{SUPPORT_LABEL[r.support_mode]} — {r.support_basis}</dd></div>
            <div><dt>Matrix table</dt><dd>{ev.matrix_table ? `Table ${ev.matrix_table}: fiber ${ev.matrix_table_fiber}, ${ev.matrix_table_pressure_atm ?? '—'} atm` : ev.matrix_table_fiber}</dd></div>
            <div><dt>Extinction-diameter origin</dt><dd>{dextClassLabel(r.dext_origin)}</dd></div>
            <div><dt>Eligible analyses (v{dataset.analysis_version})</dt><dd>{r.eligible.join(', ') || 'none'}</dd></div>
          </dl>
        </section>

        <section aria-labelledby="ins-flags"><h3 id="ins-flags">Quality flags and evidence</h3>
          <ul className="flags">
            {r.row_flags.map((f) => <li key={f}><b>{f}</b>: {dataset.rules[`quality.${f}`] ?? 'see rules'}</li>)}
            {r.sensitivity_tags.map((t) => <li key={t}><b>{t}</b>: {dataset.rules[`evidence.${t}`]}</li>)}
            {ev.pressure_source_conflict && <li><b>pressure source conflict</b>: {ev.pressure_source_conflict}</li>}
            {ev.documented_contamination_or_feature && <li><b>documented</b>: {ev.documented_contamination_or_feature}</li>}
            {ev.coated_needle_period && <li><b>coated-needle period</b>: {dataset.rules['evidence.coated_needle_period']}</li>}
            {ev.dext_caption_note && <li><b>caption</b>: {ev.dext_caption_note}</li>}
          </ul>
        </section>

        <section aria-labelledby="ins-notes"><h3 id="ins-notes">NASA test note (Appendix B caption)</h3>
          <blockquote>{ev.caption ?? 'UNKNOWN: no caption located for this test.'}</blockquote>
          <ul className="refs">
            <li>Table IX row: printed p. {ev.table_ix_printed_page} (PDF p. {ev.table_ix_pdf_page}) — <a href={reportPage(ev.table_ix_pdf_page) ?? '#'} target="_blank" rel="noreferrer">open report page</a></li>
            {ev.caption_figure && <li>Appendix B Figure {ev.caption_figure} (PDF p. {ev.caption_pdf_page}) — <a href={reportPage(ev.caption_pdf_page) ?? '#'} target="_blank" rel="noreferrer">open figure page</a></li>}
            <li>Extraction: {ev.verification_status}</li>
          </ul>
        </section>

        <section aria-labelledby="ins-prov"><h3 id="ins-prov">Provenance</h3>
          <dl className="kv mono">
            <div><dt>Source</dt><dd>{p.source_id} · DOI {p.doi} · {p.license}</dd></div>
            <div><dt>Source URL</dt><dd><a href={p.source_url} target="_blank" rel="noreferrer">{p.source_url}</a></dd></div>
            <div><dt>File · version</dt><dd>{p.file_name} · v{p.psi_file_version} (S3 {p.psi_s3_version_id})</dd></div>
            <div><dt>Raw SHA-256</dt><dd>{p.raw_sha256}</dd></div>
            <div><dt>Enrichment SHA-256</dt><dd>{p.enrichment_sha256}</dd></div>
            <div><dt>Analysis</dt><dd>v{dataset.analysis_version} · {p.analysis_summary_file} · {p.analysis_summary_sha256}</dd></div>
            <div><dt>Report</dt><dd>{p.report} · PDF SHA-256 {p.report_pdf_sha256}</dd></div>
            <div><dt>Audit</dt><dd>{p.audit_doc}</dd></div>
          </dl>
        </section>
      </div>
    </div>
  );
}

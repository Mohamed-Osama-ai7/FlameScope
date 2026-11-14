import { useEffect, useRef, useState } from 'react';
import { api, apiUrl } from '../../api/client';
import type { RunDetail } from '../../api/contracts';
import { dextClassLabel } from '../charts/specs';
import type { NumericField } from '../data/types';
import { FAMILY_LABEL, FIELD_LABEL, NUMERIC_FIELDS, SUPPORT_LABEL } from '../data/types';
import { useLab } from '../state/LabContext';

/** Modal evidence inspector: every identifier, raw vs canonical value, flag, note, reference and hash. */
export function EvidenceInspector() {
  const { dataset, byKey, selectedKey, inspectorOpen, closeInspector } = useLab();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const r = selectedKey ? byKey.get(selectedKey) : undefined;
  const [liveRun, setLiveRun] = useState<RunDetail | null>(null);
  const [loadingLive, setLoadingLive] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    if (!inspectorOpen || !r) return;
    let active = true;
    setLoadingLive(true);
    setLiveError(null);
    setLiveRun(null);

    api.listRuns({ source_record_key: r.record_key, limit: 1 })
      .then(async (page) => {
        if (!active) return;
        if (page.items.length > 0) {
          try {
            const detail = await api.getRun(page.items[0].run_id);
            if (active) setLiveRun(detail);
          } catch (e: unknown) {
            if (active) setLiveError(e instanceof Error ? e.message : 'Failed to fetch run details');
          }
        } else {
          if (active) setLiveError('Run not indexed in live database.');
        }
      })
      .catch((err: unknown) => {
        if (!active) return;
        setLiveError(err instanceof Error ? err.message : 'Database offline or not configured');
      })
      .finally(() => {
        if (active) setLoadingLive(false);
      });

    return () => { active = false; };
  }, [inspectorOpen, r?.record_key]);

  useEffect(() => {
    if (!inspectorOpen) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.querySelector<HTMLElement>('h2')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeInspector();
      if (e.key === 'Tab' && panel.current) {
        const f = [...panel.current.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"]),summary')]
          .filter((element) => element.getClientRects().length > 0);
        if (!f.length) return;
        const first = f[0];
        const last = f[f.length - 1];
        const title = panel.current.querySelector<HTMLElement>('h2');
        if (e.shiftKey && (document.activeElement === first || document.activeElement === title)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      opener.current?.focus();
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
            {ev.caption_figure && ev.caption_pdf_page && <li>Appendix B Figure {ev.caption_figure} (PDF p. {ev.caption_pdf_page}) — <a href={reportPage(ev.caption_pdf_page) ?? undefined} target="_blank" rel="noreferrer">open figure page</a></li>}
            <li>Extraction: {ev.verification_status}</li>
          </ul>
        </section>

        <section aria-labelledby="ins-db"><h3 id="ins-db">Scientific Data Platform (Live Database)</h3>
          {loadingLive && <p className="small muted">Checking live database...</p>}
          {liveRun && (
            <div className="live-db-panel">
              <p><span className="tag ok">Database Verified</span> <code>{liveRun.run_id}</code> · {liveRun.measurements.length} cells stored</p>
              <div className="table-scroll"><table className="data">
                <thead><tr><th>Variable</th><th>Live DB Value</th><th>Unit</th><th>Status</th><th>Source Column</th><th>Provenance</th></tr></thead>
                <tbody>
                  {liveRun.measurements.map((m) => (
                    <tr key={m.measurement_id}>
                      <th scope="row">{m.variable_name}</th>
                      <td className="num">{m.value !== null ? m.value : '—'}</td>
                      <td>{m.unit}</td>
                      <td><span className={`tag ${m.usable_for_analysis ? 'ok' : 'warn'}`}>{m.value_status}</span></td>
                      <td><code>{m.source_column}</code></td>
                      <td>
                        <a href={apiUrl(`/measurements/${m.measurement_id}/provenance`)} target="_blank" rel="noreferrer" className="link small">
                          Trace NASA cell ↗
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            </div>
          )}
          {!loadingLive && !liveRun && (
            <p className="small muted">
              {liveError
                ? `Live database not active (${liveError}). Displaying verified local dataset export v${dataset.analysis_version} (SHA-256 byte-level provenance).`
                : 'No live database record found.'}
            </p>
          )}
        </section>

        <section aria-labelledby="ins-prov"><h3 id="ins-prov">Provenance</h3>
          <dl className="kv mono">
            <div><dt>Source</dt><dd>{p.source_id} · <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">DOI {p.doi}</a> · {p.license}</dd></div>
            <div><dt>Dataset file</dt><dd><a href={p.source_url} target="_blank" rel="noreferrer">{p.file_name}</a> · version {p.psi_file_version}</dd></div>
            <div><dt>Retrieved</dt><dd>{p.retrieved_at_utc}</dd></div>
            <div><dt>Raw file SHA-256</dt><dd><code>{p.raw_sha256}</code></dd></div>
            <div><dt>NASA report</dt><dd><a href={p.report_url} target="_blank" rel="noreferrer">{p.report}</a> · PDF SHA-256 <code>{p.report_pdf_sha256}</code></dd></div>
          </dl>
          <details className="provenance-details"><summary>Processing and verification details</summary>
            <dl className="kv mono">
              <div><dt>Acquisition version</dt><dd>{p.psi_s3_version_id}</dd></div>
              <div><dt>Enrichment file · SHA-256</dt><dd>{p.enrichment_file} · <code>{p.enrichment_sha256}</code></dd></div>
              <div><dt>Caption index SHA-256</dt><dd><code>{p.captions_sha256}</code></dd></div>
              <div><dt>Analysis</dt><dd>v{dataset.analysis_version} · {p.analysis_summary_file} · <code>{p.analysis_summary_sha256}</code></dd></div>
              <div><dt>Audit record</dt><dd>{p.audit_doc}</dd></div>
            </dl>
          </details>
        </section>
      </div>
    </div>
  );
}

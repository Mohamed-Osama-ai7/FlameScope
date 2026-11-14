import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, api, apiUrl } from '../../api/client';
import type {
  Citation,
  CopilotResponse,
  Eligibility,
  EvidenceStatus,
  MeasurementVerification,
  RagSource,
  SearchResponse,
} from '../../api/contracts';

// Everything shown here comes from the live API (/api/v1/rag/*, /api/v1/copilot/ask). Nothing is mocked.

const ELIGIBILITY_TEXT: Record<Eligibility, string> = {
  VERIFIED_ELIGIBLE: 'Verified eligible',
  PENDING_VERIFICATION: 'Pending verification',
  ACQUIRED_BUT_EXCLUDED: 'Acquired, excluded',
  QUARANTINED: 'Quarantined',
  UNREGISTERED: 'Unregistered',
};

const STATUS_TEXT: Record<CopilotResponse['status'], string> = {
  answered: 'Answered from cited evidence',
  answered_with_ambiguity: 'Answered with ambiguity',
  comparison_blocked: 'Comparison blocked',
  abstained: 'Abstained',
};

const MEASUREMENT_TEXT: Record<EvidenceStatus, string> = {
  CLEAN: 'Reported value',
  QUALIFIED: 'Qualified value',
  INVALID: 'Flagged invalid: not a measurement',
  MISSING: 'Missing in source',
};

const VERIFICATION_TEXT: Record<MeasurementVerification, string | null> = {
  platform: 'Measurements checked against the Data Platform database.',
  loader_fallback: 'Measurement IDs follow the Data Platform contract but were not checked against its database.',
  unavailable: 'Data Platform database unavailable: numeric claims were withheld.',
  none: null,
};

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return `The Copilot service is unavailable: ${error.message}`;
    return error.message;
  }
  return error instanceof Error ? error.message : 'The request failed.';
}

function EligibilityBadge({ value }: { value: Eligibility }) {
  return <span className={`explorer-status eligibility-${value.toLowerCase()}`}>{ELIGIBILITY_TEXT[value]}</span>;
}

function MeasurementBadge({ value }: { value: EvidenceStatus }) {
  return <span className={`explorer-status measurement-${value.toLowerCase()}`}>{MEASUREMENT_TEXT[value]}</span>;
}

function SourceLegend() {
  const [sources, setSources] = useState<RagSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    api.listEvidenceSources()
      .then((items) => { if (active) setSources(items); })
      .catch((e: unknown) => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, []);
  if (error) return <p className="callout warn" role="alert">Source eligibility could not be loaded: {error}</p>;
  if (!sources) return <p className="explorer-state" aria-busy="true">Loading source eligibility…</p>;
  return (
    <ul className="warn-list compact" aria-label="Source eligibility">
      {sources.map((s) => (
        <li key={s.source_id}>
          <span>{s.source_id}{s.usable_as_evidence ? '' : ' · not used as evidence'}</span>
          <EligibilityBadge value={s.eligibility} />
        </li>
      ))}
    </ul>
  );
}

function CitationView({ citation }: { citation: Citation }) {
  return (
    <li className="citation">
      <div className="explorer-row-head">
        <span className="small">{citation.source_title} · {citation.locator_text}</span>
        <EligibilityBadge value={citation.eligibility} />
      </div>
      <blockquote>{citation.quote}</blockquote>
      {citation.measurements.map((m) => (
        <div key={m.measurement_id} className="explorer-meta measurement-row">
          <MeasurementBadge value={m.evidence_status} />
          <span>{m.variable}{m.value !== null ? ` = ${m.value} ${m.unit}` : ''}</span>
          {m.quality_flags.length > 0 && <span>flags: {m.quality_flags.join(', ')}</span>}
          <a href={apiUrl(m.provenance)} target="_blank" rel="noreferrer" title="Data Platform provenance (needs the platform database)">Provenance ↗</a>
        </div>
      ))}
      <p className="explorer-meta">
        <span>{citation.chunk_key}</span>
        <span>SHA-256 <code>{citation.source_artifact_sha256.slice(0, 12)}…</code></span>
        {citation.doi && <span>DOI {citation.doi}</span>}
      </p>
    </li>
  );
}

function CopilotAnswer({ result }: { result: CopilotResponse }) {
  const refused = result.status === 'abstained' || result.status === 'comparison_blocked';
  const verification = VERIFICATION_TEXT[result.measurement_verification];
  return (
    <section className="card" aria-live="polite" aria-label="Copilot answer">
      <div className="explorer-row-head">
        <h3>{STATUS_TEXT[result.status]}</h3>
        <span className={`explorer-status copilot-${result.status}`}>{result.status.replaceAll('_', ' ')}</span>
      </div>
      {result.status === 'abstained' && <p className="callout warn">{result.abstention_reason ?? 'No supported answer.'}</p>}
      {result.status === 'comparison_blocked' && <p className="callout warn">{result.answer}</p>}
      {!refused && (
        <ol className="claims">
          {result.claims.map((claim, i) => (
            <li key={`${i}-${claim.text.slice(0, 24)}`}>
              <p>
                {claim.text}{' '}
                <span className={`tag ${claim.evidence_type === 'analogous' ? 'warn' : ''}`}>{claim.evidence_type}</span>
                {claim.measurement_status && claim.measurement_status !== 'CLEAN' && <> <MeasurementBadge value={claim.measurement_status} /></>}
              </p>
              <ul className="citations">{claim.citations.map((c) => <CitationView key={c.chunk_id} citation={c} />)}</ul>
            </li>
          ))}
        </ol>
      )}
      {result.evidence.flagged.length > 0 && (
        <div className="callout warn"><strong>Flagged values</strong><ul>{result.evidence.flagged.map((f) => <li key={f}>{f}</li>)}</ul></div>
      )}
      {result.evidence.missing.length > 0 && (
        <div className="callout"><strong>Not in the usable evidence</strong><ul>{result.evidence.missing.map((f) => <li key={f}>{f}</li>)}</ul></div>
      )}
      {verification && <p className="small muted">{verification}</p>}
      {result.warnings.length > 0 && <ul className="small muted">{result.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      <p className="small muted">{result.notice}</p>
    </section>
  );
}

function useRequest<T>() {
  const [state, setState] = useState<{ loading: boolean; error: string | null; data: T | null }>({ loading: false, error: null, data: null });
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const run = (fn: (signal: AbortSignal) => Promise<T>) => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setState({ loading: true, error: null, data: null });
    fn(c.signal)
      .then((data) => { if (!c.signal.aborted) setState({ loading: false, error: null, data }); })
      .catch((e: unknown) => { if (!c.signal.aborted) setState({ loading: false, error: errorText(e), data: null }); });
  };
  return { ...state, run };
}

export function EvidenceCopilot() {
  const [question, setQuestion] = useState('');
  const [query, setQuery] = useState('');
  const copilot = useRequest<CopilotResponse>();
  const search = useRequest<SearchResponse>();

  const ask = (e: FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (q.length >= 3) copilot.run((signal) => api.askCopilot(q, signal));
  };
  const find = (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (q) search.run((signal) => api.searchEvidence(q, signal));
  };

  return (
    <div className="stack">
      <section className="card">
      <header className="card-head">
        <span className="eyebrow">Evidence &amp; Copilot · live API</span>
        <h2>Ask the evidence</h2>
        <p className="muted">Answers come only from eligible, cited NASA evidence and validated backend tools. Excluded,
          quarantined and unregistered sources are never used; the Copilot abstains when evidence is missing.</p>
      </header>
      </section>

      <div className="card">
        <h3>Source eligibility</h3>
        <SourceLegend />
      </div>

      <form className="card ask-form" onSubmit={ask} aria-label="Ask the Copilot">
        <label htmlFor="copilot-q"><strong>Question</strong></label>
        <textarea id="copilot-q" rows={2} value={question} maxLength={2000} onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What was the initial droplet diameter in FLEX-070?" />
        <button type="submit" disabled={copilot.loading || question.trim().length < 3}>{copilot.loading ? 'Asking…' : 'Ask'}</button>
      </form>
      {copilot.error && <p className="callout warn" role="alert">{copilot.error}</p>}
      {copilot.data && <CopilotAnswer result={copilot.data} />}

      <form className="card ask-form" onSubmit={find} aria-label="Search evidence">
        <label htmlFor="evidence-q"><strong>Evidence search</strong></label>
        <input id="evidence-q" value={query} maxLength={2000} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. FLEX-114 ambient pressure" />
        <button type="submit" disabled={search.loading || !query.trim()}>{search.loading ? 'Searching…' : 'Search'}</button>
      </form>
      {search.error && <p className="callout warn" role="alert">{search.error}</p>}
      {search.data && (
        <section className="card" aria-label="Evidence search results">
          {search.data.hits.length === 0 && <p className="explorer-state">No eligible evidence matched.</p>}
          <ol className="explorer-list">
            {search.data.hits.map((h) => {
              const flagged = h.chunk.measurements.filter((m) => m.evidence_status !== 'CLEAN');
              return (
                <li key={h.chunk.chunk_id}>
                  <div className="explorer-row-head">
                    <strong>{h.chunk.source_title}</strong>
                    <EligibilityBadge value={h.chunk.eligibility} />
                  </div>
                  <p className="explorer-meta"><span>{h.chunk.locator_text}</span><span>{h.chunk.chunk_key}</span></p>
                  <p className="small">{h.chunk.text.length > 320 ? `${h.chunk.text.slice(0, 320)}…` : h.chunk.text}</p>
                  {flagged.length > 0 && (
                    <p className="explorer-meta">
                      {flagged.map((m) => <span key={m.measurement_id}><MeasurementBadge value={m.evidence_status} /> {m.variable}</span>)}
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
          {search.data.warnings.length > 0 && <ul className="small muted">{search.data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
        </section>
      )}
    </div>
  );
}

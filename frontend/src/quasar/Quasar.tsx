import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Eligibility, RagSource } from '../api/contracts';
import { BuoyancyFlame } from './BuoyancyFlame';
import './quasar.css';

const BASE = import.meta.env.BASE_URL ?? '/';
const STATE_TEXT: Record<Eligibility, string> = {
  VERIFIED_ELIGIBLE: 'Verified eligible',
  PENDING_VERIFICATION: 'Pending verification',
  ACQUIRED_BUT_EXCLUDED: 'Excluded',
  QUARANTINED: 'Quarantined',
  UNREGISTERED: 'Unregistered',
};

const JOURNEY = [
  { n: '01', name: 'Discover', text: 'Explore audited NASA FLEX records, conditions and outcomes.', href: '#explorer', cta: 'Open the Explorer' },
  { n: '02', name: 'Ask', text: 'Questions return cited answers — or an explained refusal.', href: '#copilot', cta: 'Ask the evidence' },
  { n: '03', name: 'Compare & analyze', text: 'Unlike regimes are blocked; physics comes from code, with intervals.', href: '#comparison', cta: 'Compare runs' },
  { n: '04', name: 'Trust', text: 'Every value traces to its source, row and quality flags.', href: '#quality', cta: 'See the evidence trail' },
] as const;

function SourceLedger() {
  const [rows, setRows] = useState<RagSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    api.listEvidenceSources()
      .then((r) => { if (active) setRows(r); })
      .catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : 'request failed'); });
    return () => { active = false; };
  }, []);
  if (error) return <p className="q-ledger-note" role="status">Live source states unavailable ({error}). Nothing is assumed offline.</p>;
  if (!rows) return <p className="q-ledger-note" aria-busy="true">Reading source states from the API…</p>;
  return (
    <ul className="q-ledger" aria-label="Source eligibility, live from the API">
      {rows.map((s) => (
        <li key={s.source_id}>
          <span>{s.source_id}</span>
          <span className={`q-state q-state-${s.eligibility.toLowerCase()}`}>{STATE_TEXT[s.eligibility]}</span>
        </li>
      ))}
    </ul>
  );
}

export function Quasar({ theme, setTheme }: { theme: 'light' | 'dark'; setTheme: (t: 'light' | 'dark') => void }) {
  useEffect(() => { document.title = 'QUASAR · FlameScope'; }, []);
  return (
    <div className="quasar">
      <a className="skip" href="#q-main">Skip to content</a>
      <header className="q-bar">
        <span className="q-logo" aria-hidden="true">◉</span><strong>QUASAR</strong>
        <span className="q-bar-sub">FlameScope · UnderFitted</span>
        <span className="q-spacer" />
        <button type="button" className="ghost" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>{theme === 'dark' ? '☀ Light' : '☾ Dark'}</button>
        <a className="q-enter" href="#overview">Enter the Lab →</a>
      </header>
      <main id="q-main" tabIndex={-1}>
        <section className="q-hero" aria-labelledby="q-title">
          <img className="q-hero-img" src={`${BASE}quasar/hero_bass2.jpg`} alt="NASA photograph of a blue, rounded flame on an acrylic sample burning in microgravity aboard the ISS" />
          <div className="q-hero-shade" />
          <div className="q-hero-copy">
            <p className="q-eyebrow">NASA SPACE APPS 2026 · FLAME IN FREEFALL</p>
            <h1 id="q-title">QUASAR</h1>
            <p className="q-lead">Take away gravity and hot gas stops rising — <strong>flames turn round, dim, and play by different rules.</strong></p>
            <p className="q-sub">A scientific discovery experience that shows what the evidence supports, what can be compared, and when it must abstain.</p>
            <div className="q-cta">
              <a className="q-enter" href="#overview">Enter the Lab →</a>
              <a className="q-ghost" href="#copilot">Ask the evidence</a>
            </div>
          </div>
          <p className="q-credit">Real NASA image · BASS-II acrylic flame test aboard the ISS, 23 Jul 2014 · iss040e072900 · Credit: NASA</p>
        </section>

        <section className="q-section" aria-labelledby="q-why">
          <p className="q-eyebrow">WHY GRAVITY CHANGES FIRE</p>
          <h2 id="q-why">Switch buoyancy off</h2>
          <p className="q-text">On Earth a flame heats the air, the hot gas rises and pulls fresh oxygen in. Remove gravity and that flow nearly disappears: oxygen arrives by slow diffusion, so the flame turns round, dim and blue — and it can go out in different ways.</p>
          <BuoyancyFlame />
        </section>

        <section className="q-section" aria-labelledby="q-journey">
          <p className="q-eyebrow">THE JOURNEY</p>
          <h2 id="q-journey">From a question to evidence you can trace</h2>
          <div className="q-grid">
            {JOURNEY.map((j) => (
              <a key={j.n} className="q-card" href={j.href}>
                <span className="q-num">{j.n}</span><h3>{j.name}</h3><p>{j.text}</p><span className="q-link">{j.cta} →</span>
              </a>
            ))}
          </div>
        </section>

        <section className="q-section" aria-labelledby="q-trust">
          <p className="q-eyebrow">TRUST LEDGER · LIVE</p>
          <h2 id="q-trust">Only eligible sources may speak</h2>
          <p className="q-text">Each NASA source has a state. Only PSI-69 may be used, and only as <em>pending verification</em> — never presented as approved.</p>
          <SourceLedger />
        </section>
      </main>
      <footer className="q-foot">
        <span>Independent research prototype — not affiliated with, endorsed by, or certified by NASA; not an operational fire-safety system.</span>
        <a href="#overview">Enter the Lab →</a>
      </footer>
    </div>
  );
}

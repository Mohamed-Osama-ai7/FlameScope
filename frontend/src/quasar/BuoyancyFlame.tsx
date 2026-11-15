import { useEffect, useRef, useState } from 'react';
import { flameGeometry } from './buoyancy';

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** Signature animation 1: "Buoyancy off". Gravity is scrubbed from 1 g to 0 g (auto-plays once when visible). */
export function BuoyancyFlame() {
  const [g, setG] = useState(1);
  const frame = useRef<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const played = useRef(false);

  const play = () => {
    if (frame.current) cancelAnimationFrame(frame.current);
    if (prefersReducedMotion()) { setG(0); return; }
    const start = performance.now();
    const duration = 3600;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      setG(1 - eased);
      frame.current = t < 1 ? requestAnimationFrame(step) : null;
    };
    setG(1);
    frame.current = requestAnimationFrame(step);
  };

  useEffect(() => {
    const el = root.current;
    if (!el || typeof IntersectionObserver === 'undefined') return undefined;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && !played.current) { played.current = true; play(); }
    }, { threshold: 0.5 });
    io.observe(el);
    return () => { io.disconnect(); if (frame.current) cancelAnimationFrame(frame.current); };
  }, []);

  const geo = flameGeometry(g);
  const label = g > 0.66 ? 'Buoyant convection' : g > 0.33 ? 'Buoyancy fading' : 'Diffusion only';
  const arrows = [-70, -35, 35, 70];
  return (
    <div className="q-buoyancy" ref={root}>
      <svg viewBox="0 0 320 320" role="img" aria-labelledby="q-flame-title q-flame-desc" className="q-flame-svg">
        <title id="q-flame-title">Schematic flame at {g.toFixed(2)} g</title>
        <desc id="q-flame-desc">{label}: {g > 0.5
          ? 'hot gas rises and pulls fresh air in from below, so the flame is tall and luminous.'
          : 'oxygen arrives mainly by diffusion, so the flame is round, wider and dimmer.'}</desc>
        <defs>
          <radialGradient id="q-glow">
            <stop offset="0%" stopColor={geo.core} stopOpacity="0.95" />
            <stop offset="70%" stopColor={geo.core} stopOpacity="0.35" />
            <stop offset="100%" stopColor={geo.core} stopOpacity="0" />
          </radialGradient>
        </defs>
        {[1, 1.35, 1.7].map((k) => (
          <circle key={k} cx="160" cy="190" r={geo.haloRadius * k * 0.8} className="q-ring" style={{ opacity: geo.diffusion * (0.5 / k) }} />
        ))}
        {arrows.map((dx) => (
          <g key={dx} className="q-arrow" style={{ opacity: geo.convection }}>
            <line x1={160 + dx} y1={300} x2={160 + dx * 0.55} y2={250} />
            <polyline points={`${160 + dx * 0.55 - 5},${258} ${160 + dx * 0.55},${250} ${160 + dx * 0.55 + 5},${258}`} />
          </g>
        ))}
        <g className="q-plume" style={{ opacity: geo.convection }}>
          <line x1="160" y1={190 - geo.height + 40} x2="160" y2="18" />
          <polyline points="154,28 160,18 166,28" />
        </g>
        <path d={geo.path} fill="url(#q-glow)" stroke={geo.core} strokeOpacity="0.8" strokeWidth="1.5" />
        <circle cx="160" cy="190" r="7" className="q-droplet" />
      </svg>
      <div className="q-buoyancy-controls">
        <label htmlFor="q-gravity">Gravity <strong>{g.toFixed(2)} g</strong> · {label}</label>
        <input id="q-gravity" type="range" min={0} max={1} step={0.01} value={g}
          aria-valuetext={`${g.toFixed(2)} g, ${label}`}
          onChange={(e) => { if (frame.current) cancelAnimationFrame(frame.current); setG(Number(e.target.value)); }} />
        <div className="q-scale"><span>0 g · microgravity</span><button type="button" className="ghost" onClick={play}>Replay</button><span>1 g · Earth</span></div>
        <p className="q-caption">Schematic, not a simulation: shape and flow are qualitative. Measured NASA values live in the Lab.</p>
      </div>
    </div>
  );
}

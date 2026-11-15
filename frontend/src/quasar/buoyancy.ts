/**
 * Schematic flame geometry as a function of effective gravity g (1 = Earth, 0 = microgravity).
 *
 * Qualitative physics it encodes (not a simulation): with buoyancy, hot products rise and draw fresh air in from
 * below, so the flame is tall, tip-pinched and luminous (soot); without buoyancy, oxygen reaches the flame mainly
 * by diffusion, so it is near-spherical, wider-spread and dimmer/bluer.
 */
export interface FlameGeometry {
  path: string; // closed SVG path of the visible flame envelope
  height: number; // tip-to-base height (px)
  width: number; // max width (px)
  haloRadius: number; // diffusion zone radius (px)
  convection: number; // 0..1 strength of the buoyant inflow / plume arrows
  diffusion: number; // 0..1 visibility of the diffusion rings
  core: string; // flame colour (hex): luminous yellow-orange at 1 g, blue at 0 g
}

const K = 0.5523; // cubic Bezier circle constant

export function clampG(g: number): number {
  return Number.isFinite(g) ? Math.min(1, Math.max(0, g)) : 0;
}

function mix(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `#${pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, '0')).join('')}`;
}

export function flameGeometry(gIn: number, cx = 160, cy = 190, r = 58): FlameGeometry {
  const g = clampG(gIn);
  const top = r * (1 + 1.6 * g); // tip distance above centre: 1 r (sphere) .. 2.6 r (teardrop)
  const rx = r * (1 - 0.18 * g); // a buoyant flame is narrower
  const tipCtl = r * (K - 0.45 * g); // pinch of the tip
  const shoulder = top * K * (1 - 0.3 * g);
  const f = (n: number) => n.toFixed(2);
  const path = [
    `M ${f(cx)} ${f(cy + r)}`,
    `C ${f(cx + K * rx)} ${f(cy + r)} ${f(cx + rx)} ${f(cy + K * r)} ${f(cx + rx)} ${f(cy)}`,
    `C ${f(cx + rx)} ${f(cy - shoulder)} ${f(cx + tipCtl)} ${f(cy - top)} ${f(cx)} ${f(cy - top)}`,
    `C ${f(cx - tipCtl)} ${f(cy - top)} ${f(cx - rx)} ${f(cy - shoulder)} ${f(cx - rx)} ${f(cy)}`,
    `C ${f(cx - rx)} ${f(cy + K * r)} ${f(cx - K * rx)} ${f(cy + r)} ${f(cx)} ${f(cy + r)}`,
    'Z',
  ].join(' ');
  return {
    path,
    height: top + r,
    width: 2 * rx,
    haloRadius: r * (1.25 + 0.6 * (1 - g)),
    convection: g,
    diffusion: 1 - g,
    core: mix('#4fa8ff', '#ffb347', g),
  };
}

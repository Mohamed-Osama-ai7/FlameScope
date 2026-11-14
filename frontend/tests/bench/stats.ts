export type Stat = { n: number; median: number; p95: number; min: number; max: number };

/** Median and nearest-rank p95 (for n < 20 the p95 is a high order statistic; for n = 5 it equals the maximum). */
export function stat(xs: number[]): Stat {
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
  const p95 = s[Math.min(s.length - 1, Math.ceil(0.95 * s.length) - 1)];
  const r = (x: number) => Math.round(x * 10) / 10;
  return { n: s.length, median: r(mid), p95: r(p95), min: r(s[0]), max: r(s[s.length - 1]) };
}

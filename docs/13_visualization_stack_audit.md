# 13 — Visualization Stack Audit (2026-11-13)

Scope: verify whether the Scientific Exploration Lab's visualization and test stack meets current
professional standards, and modernise it only where compatibility and measurable value justify it.
No scientific code, data, rules or conclusions are changed by this work.

Environment: Windows 11, Node 24.21.0, npm 11.19.0, system Chrome. Release notes were read from the
official GitHub releases / changelogs (Plotly, react-plotly.js, TanStack Table docs, Playwright,
axe-core).

## Part 1 — Pre-change audit and recommendation (written BEFORE any dependency was modified)

> **Superseded where it differs by Part 1b below.** Part 1 is kept unchanged as the first draft so the
> corrections stay visible. Two statements in it were revised after review: the Plotly candidate set (4.3.0
> *is* a Cartesian package version, and v4 turns the cloud-upload button on by default) and the Playwright
> browser-download remark (already corrected inline).

### 1.1 What is installed today

| Package | Installed | Declared | Licence | Node | Role / note |
|---|---|---|---|---|---|
| plotly.js-cartesian-dist-min | 2.35.2 | exact | MIT | — | the engine actually bundled (1,327 KB raw / 435 KB gzip) |
| react-plotly.js | 2.6.0 | exact | MIT | — | wrapper, peer `plotly.js > 1.34.0`, `react > 0.13` |
| **plotly.js (full)** | **4.3.0** | *not declared* | MIT | ≥ 22 | **auto-installed peer** of react-plotly.js: 97 MB, 226 extra packages, never imported or bundled; it is a *different version* from the engine that actually runs |
| @tanstack/react-table (+ table-core) | 8.20.6 (8.20.5) | exact | MIT | ≥ 12 | observations table |
| @playwright/test / playwright | 1.49.1 | exact | Apache-2.0 | ≥ 18 | browser tests |
| **playwright-core** | **1.65.0 *and* 1.49.1** | — | Apache-2.0 | ≥ 20 | **version skew**: axe's peer pulled 1.65.0 at the top level while @playwright/test uses its own nested 1.49.1 |
| @axe-core/playwright / axe-core | 4.10.1 / 4.10.3 | exact | MPL-2.0 | — | accessibility audit (test-only) |
| @types/react-plotly.js → @types/plotly.js | 2.6.3 → 3.0.15 | exact | MIT | — | types |

Install scripts in the lockfile (inspected, not assumed):

| Package | Script | What it does | Needed? |
|---|---|---|---|
| es5-ext 0.10.64 | `postinstall` | prints a political message only when the system time zone is a Russian one; otherwise a no-op | No. Arrives **only** through the unused full `plotly.js` peer (via gl-text → es6-weak-map) |
| esbuild 0.25.12 (vite, dev) | `postinstall: node install.js` | validates / optimises the platform binary; the binary itself ships as the optional package `@esbuild/win32-x64`, already installed | Not required: build, tests and dev server have all run with this script unapproved |
| fsevents (dev) | native build | macOS only; not installed on Windows | n/a |

### 1.2 Latest stable releases and breaking changes that matter

| Package | Latest stable | Relevant breaking changes (official notes) | Exposure in this code |
|---|---|---|---|
| plotly.js 3.x (3.7.0) | 3.7.0 (2026-07) | Removed string `title`, `titlefont` & co, `transforms`, `autotick`, gl2d/pointcloud/heatmapgl, jQuery events, AMD; Node 18 for dev | None used: all titles are `{text}` objects; no transforms/maps/3D |
| plotly.js 4.x (4.3.0) | 4.3.0 (2026-11-10, three days old) | **Colour engine switched TinyColor → culori** (decimal-fraction `rgb()`, `hsv()` no longer accepted, contrast-picked label colours); mapbox traces and MathJax v2 removed; `tickmode` default `sync` for overlaying axes; `splom.matches`, `geo.fitbounds` defaults; hover/click-anywhere values; Node ≥ 22 (development of plotly itself) | Colours are hex or `rgba(0,0,0,0)` (valid in culori); heatmap text colour is set explicitly; no maps, MathJax, splom or overlaying axes |
| react-plotly.js 3.0.0 | 2026-06 | **Dropped plotly.js 1.x/2.x** (peer now `>= 3.0.0`) and React < 18 | **Forces the engine off 2.x if the wrapper is upgraded** |
| react-plotly.js 4.x (4.1.0) | 2026-07 | Native ESM; ships TypeScript declarations; class → hooks; `ref.current.el` → `ref.current`; `onPurge`/`Plotly.purge` now run on unmount; correct re-init after React StrictMode remount; removed bogus `onClickAnywhere`/`onHoverAnywhere` props | We attach no refs; we use `onInitialized`, `onUpdate`, `onClick`; the app runs under StrictMode. Peers: `plotly.js >= 3.0.0`, `react ^18 \|\| ^19` — so 4.x of the wrapper works with Plotly **3.x or 4.x** |
| @tanstack/react-table 9.x (9.3.1) | 9.3.1 (2026-10) | **API rewrite**: `useReactTable` → `useTable`, `tableFeatures()` registry, row-model factories moved, `onStateChange` removed; Node ≥ 20 | Would need the table rewritten; benefit (tree-shaking) is negligible for 274 rows |
| @tanstack/react-table 8.x | 8.21.3 (2025-04) | none (same major) | no defect or measurable gain found |
| @playwright/test 1.65.0 | 2026-11-05 | Between 1.49 and 1.65: removed `Page#accessibility`, `_react`/`_vue` selectors, launch `devtools`, MV2 extensions, deprecated APIs; `screen` forwarded from device descriptors; Node 20 no longer tested (22/24/26); bundled Chromium 158, Firefox 159, WebKit 27.2 | None used by these tests; Node 24 is supported |
| axe-core / @axe-core/playwright 4.14.0 | 2026-10 | no breaking changes 4.10.3 → 4.14.0; many rule fixes (colour-contrast stacking-context fixes, ARIA rules, `label-content-name-mismatch` now on by default); `@axe-core/playwright` 4.14.0 needs Node ≥ 22.12 | Node 24 fine |

### 1.3 Findings

1. **Engine/wrapper pairing is correct today but frozen on an unsupported line.** Wrapper 2.6.0 is
   designed for Plotly 1.x/2.x; Plotly 2.x has had no release since 2.35.3 (2024-12) and wrapper 3.0
   dropped it.
2. **The full `plotly.js` peer is dead weight and misleading**: 97 MB, 226 packages and the only
   source of the `es5-ext` install script, installed at a different version (4.3.0) than the engine
   that runs (2.35.2). Wrapper 4.x declares the same peer, so simply upgrading does not remove it.
3. **Version skew in the test stack**: two copies of `playwright-core` (1.49.1 nested, 1.65.0 top-level).
4. **The old Playwright tests against engines about two years old**: 1.49.1 pins Firefox 132 and
   WebKit 18.2; 1.65.0 pins Chromium 158, Firefox 159 and WebKit 27.2. (An earlier draft of this
   audit claimed the old browser CDN was retired; that was wrong: the old `azureedge.net` URLs
   redirect to a working Microsoft host.)
5. Nothing in the code uses any removed or changed Plotly, wrapper, Playwright or axe API.

### 1.4 Recommendation (to be validated empirically before adoption)

| Package | Recommendation | Reason |
|---|---|---|
| plotly.js engine | **Move 2.35.2 → 3.7.0** (cartesian build, 460 KB gzip, +25 KB); **evaluate 4.3.0** (490 KB gzip, +55 KB) in an isolated copy and adopt only if it shows measurable benefit | 3.x is a supported line and unlocks wrapper 4.x; v4 adds nothing the lab uses, costs +12.6 % bytes, changes the colour engine and is three days old |
| react-plotly.js | **2.6.0 → 4.1.0** | hooks rewrite, purge-on-unmount, StrictMode fix, shipped types (drops `@types/react-plotly.js`); peer-compatible with Plotly ≥ 3 |
| Plotly peer | **Eliminate the full `plotly.js`** by declaring `"plotly.js": "npm:plotly.js-cartesian-dist-min@<version>"` as the single direct engine dependency (satisfies the wrapper's peer with the cartesian build; no duplicate engine, no es5-ext) | keeps the cartesian-only advantage |
| @tanstack/react-table | **Retain 8.20.6** | no defect or measurable gain from 8.21.3; v9 is a rewrite not justified for a 274-row table |
| @playwright/test | **1.49.1 → 1.65.0** | removes the duplicate playwright-core (and the type mismatch it causes with `@axe-core/playwright`), current Firefox 159 / WebKit 27.2 / Chromium 158 for cross-browser QA |
| axe-core + @axe-core/playwright | **→ 4.14.0** | newer rule set evaluated on the same pages; no breaking changes |
| Install scripts | **Leave `esbuild` unapproved; remove `es5-ext` with the peer; ignore `fsevents`** | justified in 1.1 |
| ECharts / D3 | **Not introduced** | no demonstrated requirement |

Acceptance criteria for each change: type check, build, unit tests, all functional / visual /
accessibility tests pass; rendering benchmarks no worse than the current stack beyond noise;
visual diffs inspected by eye, not blindly re-baselined.

## Part 1b — Corrected compatibility matrix (still BEFORE any dependency change)

### 1b.1 What the correction round changed

| First draft | Corrected |
|---|---|
| Compare Cartesian 3.7.0 and 4.3.0 | Compare **3.7.0, 4.1.2, 4.2.0 and 4.3.0**. The review note called 4.2.0 the latest stable Cartesian package; the registry shows `plotly.js-cartesian-dist-min` **4.3.0 (2026-11-10)** as `latest` (metadata: "minified plotly.js cartesian distributed bundle", 1.5 MB). It is a Cartesian build, not the full `plotly.js` (which also has a 4.3.0, and is the auto-installed peer we want to remove) |
| Plotly v4 colours: "hex is safe" | Audit all colour literals and add an automated check (1b.4) |
| Nothing on cloud upload | **Verified in the bundle source: `showSendToCloud` defaults to `false` in 3.7.0 but `true` in 4.2.0 and 4.3.0.** Any v4 engine adds an "Upload to Cloud" button (it posts chart data to Plotly's cloud) unless `showSendToCloud: false` is set. We set it explicitly (and remove the `sendDataToCloud` button) for every variant, with a test |
| TanStack v9 "not justified" | Pre-registered migration criteria and a measured scratch port (1b.6) |
| Browser CDN | the first-draft claim was wrong (old URLs redirect to a working host); the old engines are simply old |

### 1b.2 Plotly Cartesian candidates (measured from the published tarballs)

| Package version | Published | Raw KB | gzip KB | Δ gzip vs 2.35.2 | `showSendToCloud` default | Relevant notes (official releases) |
|---|---|---|---|---|---|---|
| 2.35.2 (current) | 2024-12 | 1,327 | 435 | — | false | unsupported line: no release since 2.35.3 (Dec 2024); wrapper 3.0 and later dropped it |
| 3.7.0 | 2026-07-03 | 1,391 | 461 | +26 | **false** | last 3.x; the v3 removals do not touch this code |
| 4.1.2 | 2026-10-05 | 1,472 | 488 | +53 | true | `ResizeObserver` for responsive resizing; redraw when a font finishes loading; type fixes |
| 4.2.0 | 2026-10-29 | 1,479 | 490 | +55 | true | keeps cartesian traces aligned under automargin titles; MathJax href XSS fix; scattergl hover-freeze fix |
| 4.3.0 | 2026-11-10 | 1,480 | 490 | +55 | true | **prototype-pollution fix in plot API calls**; `domainpad` |

All five are MIT, ship **no TypeScript types and declare no peer or engine requirements**, and are Cartesian-only:
none of the geo, 3D, Sankey, map, polar, SPLOM, parcoords, sunburst or treemap trace types is present in any of
them (checked by searching each bundle for its trace registrations). So `@types/plotly.js` (DefinitelyTyped,
3.0.15) remains an explicit dev dependency in every variant; it targets the Plotly 3 API, so for v4 engines it is
close but not exact (a small type-fidelity cost of v4).

v4 changes that matter here (official 4.0.0 notes): colour parser replaced (TinyColor to culori), mapbox and
MathJax v2 removed, Chart Studio config removed, `tickmode` / `splom` / `geo.fitbounds` defaults, hover and
click-anywhere values, Node 22 or later for developing plotly.js itself (the dist bundle has no engine requirement).

### 1b.3 Engine / wrapper / types architecture

* **react-plotly.js 4.1.0** with its documented `factory` API: `createPlotlyComponent(Plotly)` takes the engine as
  `unknown`, so the Cartesian build is injected explicitly. Its declared peers are `plotly.js >= 3.0.0` and
  `react ^18 || ^19`; it ships its own `.d.ts` (deliberately not depending on `@types/plotly.js`), so
  `@types/react-plotly.js` is dropped.
* **Single engine, no duplicate:** declare `"plotly.js": "npm:plotly.js-cartesian-dist-min@<version>"` as the one
  direct engine dependency. That satisfies the wrapper's `plotly.js` peer with the Cartesian build, so npm does not
  install the full 97 MB package (nor its 226 packages and the `es5-ext` install script), and no second copy of the
  engine exists. The code imports the engine from one module (`src/lab/plotly.ts`).
* **Ref audit (done):** no `ref` is attached to `<Plot>`; the code only uses the `graphDiv` argument of
  `onInitialized` / `onUpdate`. The wrapper-4 change `ref.current.el` to `ref.current` therefore does not apply.
  The other refs in the app are plain DOM refs (inspector focus trap, table row scroll, a reduced-motion snapshot).

### 1b.4 Plotly v4 colour audit

Every colour that reaches Plotly comes from `src/lab/charts/specs.ts`, `src/lab/state/LabContext.tsx` (CSS
variables resolved with `getComputedStyle`) and the palette constants, and is either a 6-digit hex (`#rrggbb`) or
`rgba(0,0,0,0)`. None uses `hsv()`, decimal-fraction `rgb()`, or other removed formats. The heatmap sets its text
colour explicitly, so the v4 contrast-picked label colour is not relied on. This is **enforced** by a unit test that
scans every colour attribute of every generated figure, and by the visual-regression screenshots.

### 1b.5 Test stack

Align everything to Playwright 1.65.0: `@playwright/test`, `playwright` and `playwright-core` all 1.65.0, and
`@axe-core/playwright` / `axe-core` 4.14.0 (`@axe-core/playwright` needs Node 22.12 or later; Node 24 is installed).
Acceptance: `npm ls playwright-core playwright @playwright/test` shows one version of each; `tsc` over the test code
passes (today it fails with the `Page` type mismatch caused by the skew); real Chromium, Firefox and WebKit runs
(browser builds downloaded with permission, about 200 MB).

### 1b.6 TanStack Table: V8 vs V9.3.1

V9 (stable 9.3.1, Node 20 or later, React 18 or later) is an API rewrite: `useReactTable` becomes `useTable`, a
`tableFeatures()` registry, row-model factories moved into it, `onStateChange` removed. **Decision rule fixed in
advance:** keep V8 unless a scratch port of the lab table to V9 (a) cuts the production bundle by at least 10 KB
gzip or makes 274-row sort/search faster than run-to-run noise, **and** (b) passes the same tests. The port is done
in an isolated copy so the project is never put at risk; the result is reported whatever it shows.

### 1b.7 Install scripts and transitive dependencies

Audit after the change, from the real lockfile and `node_modules`: every package with an install script (script
read, not assumed), every distinct licence in the installed tree, `npm audit`, and duplicate-package checks.
Targets: no `es5-ext`; `esbuild` left unapproved if the build still works; no copy of the full `plotly.js` engine
in the tree, and **none of its code in the production bundle** (checked by searching the built assets for
non-Cartesian trace registrations and by the single Plotly chunk's size).

### 1b.8 Benchmark method and acceptance

Identical harness and parameters for every variant (Part 2). The unchanged stack is re-baselined first, quietly,
with strict timeouts (30 s per download wait, 5 min per test, 25 min for the whole run). A variant is adopted only
if all tests pass and its real-data interaction timings are within the baseline's own run-to-run variation
(measured from two baseline runs) or better; the byte cost is reported next to the benefit rather than hidden.


**Selection rule for the Plotly engine, fixed before any variant is installed.** Each of 3.7.0, 4.1.2, 4.2.0 and
4.3.0 is installed as the single aliased engine behind react-plotly.js 4.1.0 and put through: type check, unit tests,
production build, bundle inspection, the 13 functional end-to-end tests, and the identical benchmark. A variant is
*eligible* if all of that passes and its real-data timings are within the baseline's ±5 % noise band (or better).
Among eligible variants, the tie-break is **safety, then recency**:

1. `showSendToCloud: false` and the removal of the `sendDataToCloud` button are applied to every variant and tested,
   so v4's cloud-upload default is neutralised rather than a reason to avoid v4.
2. Plotly has published no 3.x release since 3.7.0 (2026-07-03) while 4.x ships about monthly, so security fixes
   (for example 4.3.0's prototype-pollution fix in plot API calls) will not reach 3.x. If a v4 variant is eligible,
   the newest eligible stable v4 release is therefore preferred over 3.7.0, **provided** the guards for v4's
   behaviour changes (cloud button, colour-format test, inspected screenshots) all pass.
3. The extra ~29 KB gzip of v4 over 3.7.0 is reported, not hidden. The inputs to Plotly in this app are static,
   verified data, so the practical exposure to the prototype-pollution issue is low; the argument for v4 is
   maintenance headroom, not an exploitable hole.
4. If no v4 variant is eligible, 3.7.0 is adopted; if nothing is eligible, the current versions are retained.


## Part 1c — Registry, tarball and advisory verification (done independently of the npm CLI and web pages)

All queries went straight to `https://registry.npmjs.org` (npm's configured registry) with `curl`, and tarballs were
downloaded and hashed. Raw packuments were saved in the scratch area; the results are reproduced here.

### 1c.1 The two packages are distinct, and Cartesian 4.3.0 exists

| Field | `plotly.js-cartesian-dist-min` | `plotly.js-dist-min` (full engine) |
|---|---|---|
| `dist-tags.latest` | **4.3.0** (`rc`: 4.0.0-rc.0) | 4.3.0 (`rc`: 4.0.0-rc.0) |
| Description | "minified plotly.js cartesian distributed bundle" | "minified plotly.js distributed bundle" |
| 4.3.0 published | 2026-11-10 21:44:23Z | 2026-11-10 21:45:57Z |
| 4.3.0 unpacked size | 1,518,867 B | 6,197,199 B |
| 4.3.0 `dist.integrity` | `sha512-1ioBF15r2LLO7wfJ+UqunVDI2NmAwmyDmx8M+yuP2lG9YjfMfRWNeo94FHyP2ThQB1o3mMkF/Rs3RnCLExIjzw==` | `sha512-Vv1gkRoFXiCDmGDe1q22jEvTSJgB+nASs5tzkqotUTIXfP++N0hAOaqVN3QMgGPxsuBRviupX8+1dJX/V6jqgA==` |
| 4.3.0 tarball | `…/plotly.js-cartesian-dist-min/-/plotly.js-cartesian-dist-min-4.3.0.tgz` | `…/plotly.js-dist-min/-/plotly.js-dist-min-4.3.0.tgz` |

The review note that npm's web pages showed Cartesian 4.2.0 does not match the registry; the registry's `modified`
timestamp for the Cartesian package is 2026-11-10T21:44:23Z. The web page was most likely stale or cached; it cannot
be explained from here, and the registry is authoritative. Cartesian versions and publish dates (UTC):
3.7.0 2026-07-03, 4.0.0 2026-08-24, 4.1.0 2026-09-08, 4.1.1 2026-09-14, 4.1.2 2026-10-05, 4.2.0 2026-10-29,
4.3.0 2026-11-10. The full package's 4.x publishes are within two minutes of the matching Cartesian ones.

### 1c.2 Tarball integrity and trace modules

Every tarball below was downloaded and its SHA-512 recomputed: **all match the registry `dist.integrity`**. The
installed engine in `package-lock.json` (alias `node_modules/plotly.js` → `plotly.js-cartesian-dist-min` 4.3.0) carries the
same `sha512-1ioBF15r…` integrity.

| Package@version | Tarball bytes | Bundle raw KB | Trace modules |
|---|---|---|---|
| cartesian 3.7.0 | 477,385 | 1,391 | 12 |
| cartesian 4.1.2 | 505,202 | 1,472 | 12 |
| cartesian 4.2.0 | 507,556 | 1,479 | 12 |
| cartesian 4.3.0 | 507,952 | 1,480 | 12 |
| **full** dist-min 4.3.0 | 1,669,142 | 4,729 | **47** |

The four Cartesian builds register the identical 12 traces: bar, box, contour, heatmap, histogram, histogram2d,
histogram2dcontour, image, pie, scatter, scatterternary, violin. The full package registers 47; the 35 that exist
only there are barpolar, candlestick, carpet, choropleth, choroplethmap, cone, contourcarpet, densitymap, funnel,
funnelarea, icicle, indicator, isosurface, mesh3d, ohlc, parcats, parcoords, quiver, sankey, scatter3d,
scattercarpet, scattergeo, scattergl, scattermap, scatterpolar, scatterpolargl, scattersmith, splom, streamtube,
sunburst, surface, table, treemap, volume, waterfall. **The full package is not an equivalent candidate and was not
substituted.** (So the Cartesian build has no WebGL `scattergl`; a WebGL comparison would need a second, larger engine.)

Caveat on "no map code": every Cartesian bundle, including the current 2.35.2, embeds the MapLibre **stylesheet**
(`.maplibregl-*` CSS injected through a `<style>` element: 13 KB in 2.35.2, 62 KB in 3.7.0, 80 KB in 4.x). None
contains MapLibre JavaScript or registers a map trace. The bundle check therefore asserts "no map JavaScript" and
reports the CSS size instead of claiming zero MapLibre strings.

### 1c.3 Security claims: what is actually verified

| Claim | Verification | Conclusion |
|---|---|---|
| "4.3.0 fixes a prototype-pollution vulnerability" | PR plotly/plotly.js#8168 (merged 2026-11-10): "fix potential prototype pollution when expanding/merging object paths"; changes `src/lib/extend.js` and `src/lib/index.js` so only own properties are considered. The PR says "potential"; it has **no CVE or GHSA** | A hardening bug fix, **not a published advisory**. Not used as an upgrade justification |
| Published advisories for the npm package `plotly.js` | GitHub advisory database: GHSA-wjc4-73q6-gv3m / CVE-2023-46308 (prototype pollution, fixed 2.25.2) and GHSA-2fqv-h3r5-m4vf / CVE-2017-1000006 (XSS, fixed 1.16.0). The plotly/plotly.js repository itself lists 0 published security advisories | Neither affects any version compared (2.35.2, 3.7.0 and 4.x are all above both fix versions) |
| npm's advisory database | `POST /-/npm/v1/security/advisories/bulk` for the cartesian 3.7.0 / 4.1.2 / 4.2.0 / 4.3.0, full dist-min 4.3.0 and react-plotly.js 4.1.0 returned `{}` | no known advisories |
| 4.2.0 "XSS via `javascript:` URLs in MathJax `\href`" (PR #8051) | touches `src/lib/svg_text_utils.js` and hover rendering for MathJax text | not applicable: the app never loads MathJax and has no tex text; no GHSA published |
| 4.1.1 `maplibre-gl` CVE | map traces only | not applicable: no MapLibre JavaScript and no map trace in any Cartesian bundle |

**Amendment to the selection rule in Part 1b.8.** Item 2 of the pre-registered tie-break preferred v4 because "security
fixes … will not reach 3.x". Verification shows no published advisory behind that fix, so security is **not** a
reason to prefer v4 and that item is withdrawn. The governing criterion is the one stated for this task: the newest
verified Cartesian version that passes every correctness, compatibility and performance gate without losing
required behaviour.

## Part 2 — Benchmark method

Everything below measures **real browser rendering** (Plotly SVG in Chrome), not only data transformation.

| Item | Detail |
|---|---|
| Machine | Windows 11, 12 logical CPUs, 32 GB RAM, Intel UHD Graphics (hardware-accelerated Chrome) |
| Browser | system Chrome (headless, `HeadlessChrome/157`), launched with `--enable-precise-memory-info --js-flags=--expose-gc` |
| Harness (synthetic) | `frontend/bench/` + `tests/bench/render.bench.ts`, built and served separately (port 4190). Renders through the **same code path as the lab**: `viewData` → `scatterFigure` → `<Plot>` (react-plotly.js + the lazy cartesian engine). Two panels (Methanol / Heptane, free-floating), SVG scatter traces, seeded synthetic points flagged `synthetic: true` |
| Real data | `tests/bench/app.bench.ts` drives the production app build (port 4180) with the 274 verified FLEX records; interactions are timed **in the page** with `performance.now()` so no Playwright protocol latency enters them |
| Warm-up / repetitions | synthetic: 2 warm-up mounts, then 15 / 10 / 5 renders and 15 / 10 / 5 updates for 1k / 10k / 50k points (exports 10 / 5 / 3); real data: 3 warm-up rounds, 20 repetitions (cold load: 1 discarded + 10 fresh contexts with empty cache) |
| Statistics | median and nearest-rank p95 (for 5 repetitions p95 equals the maximum, for 3 the maximum as well; treat p95 at small n as "worst observed") |
| Metrics | *ready* = until the wrapper reports the plot drawn; *painted* = until two animation frames later; *spec build* = JavaScript time to turn records into a Plotly figure |
| Memory | DevTools Protocol with forced garbage collection: JS heap and DOM node counts retained per mount, and a leak check after unmount (the older `performance.memory` figure was dropped: it ignores DOM memory and was too noisy) |
| Isolation | no other CPU-heavy work ran during a benchmark; the harness is never imported by the app, synthetic data is rejected by the lab loader and every export, and no benchmark output feeds any scientific file |
| Caveats | single machine, single run per variant; timings vary by roughly ±10 % between runs; headless Chrome; the Cartesian-only engine has no WebGL trace, so no WebGL numbers exist; Firefox/WebKit expose no heap or breakdown data |

## Part 3 — Baseline on the unchanged stack (documented BEFORE any upgrade)

Stack: Plotly cartesian 2.35.2 + react-plotly.js 2.6.0 + @tanstack/react-table 8.20.6 + Playwright 1.49.1.
Run: 2026-11-13, Chrome (headless), strict timeouts, machine otherwise idle; 6 of 6 benchmark tests passed in 1.8 min.
Raw results: `frontend/tests/bench/__results__/render-v0-plotly2.35.2-rp2.6.0-chromium.json` and `app-v0-…json`.

**Run-to-run variation (measured, not assumed).** This methodology was run twice on the unchanged stack (the first
of the two had light, brief network checks running alongside, and its export test hung on Chrome's 11th-download
prompt, since fixed). Medians of the two runs for initial render → ready: 1k points 47.2 vs 48.7 ms (+3 %),
10k points 295.0 vs 305.2 ms (+3.5 %), 50k points 1,362 vs 1,384 ms (+1.6 %); filter update 23.7 vs 24.0 / 180.8 vs
184.9 / 739.1 vs 740.6 ms. **Treat differences below about ±5 % as noise.** (A still earlier run without the
DevTools Protocol instrumentation gave 42.2 / 273 / 1,317 ms; instrumentation itself adds a few percent, so it is
not comparable and is not used.)

What the numbers say about this application:
* SVG rendering scales about linearly, roughly 27 µs per point (1,000 → 48.7 ms; 10,000 → 305 ms; 50,000 → 1.38 s).
* The lab's real charts draw about 28–120 points per panel (209 free-floating records across all views), i.e. well
  under 1k points: **real-data chart updates take 14–21 ms** and selection → inspector takes about 4 ms.
* No leak: after unmount and forced GC the DOM node count returns to (or below) its starting value at every size,
  and residual JS heap is 0.9–1.5 MB regardless of point count.
* The DevTools script/layout CPU split was dropped: at 50k points it summed to about 34 ms against a 1.38 s render,
  so it does not capture where the time goes and would mislead.

"Initial render → ready" is the time until the wrapper reports the plot drawn; "painted" adds two animation frames.
Synthetic charts: two panels (Methanol / Heptane, free-floating), `scatter` SVG traces. Export timings for the
synthetic harness call `Plotly.toImage` directly (SVG 1,200 px; PNG at scale 2); real-data export timings are
end-to-end click-to-download including Playwright overhead.


### Synthetic render (scatter), chromium: median / p95 ms


**1,000 points**

| Metric | v0-plotly2.35.2-rp2.6.0 |
|---|---|
| Initial render → ready | 48.7 / 51.4 |
| Initial render → painted | 52.6 / 77.2 |
| Figure spec build | 2.1 / 2.3 |
| Filter update → ready | 24 / 45.7 |
| Selection highlight → ready | 33.7 / 40 |
| Export SVG | 40.9 / 64.8 |
| Export PNG | 90 / 103.1 |
| Retained JS heap per mount (MB) | 0.8 / 1.2 |
| Retained DOM nodes per mount | 1330 / 1330 |
| Leak check (after unmount + GC) | {"heapMBAfterUnmountVsBefore":0.9,"domNodesAfterUnmountVsBefore":-1301} |

**10,000 points**

| Metric | v0-plotly2.35.2-rp2.6.0 |
|---|---|
| Initial render → ready | 305.2 / 339.2 |
| Initial render → painted | 336.9 / 378 |
| Figure spec build | 17.4 / 18.8 |
| Filter update → ready | 184.9 / 218.8 |
| Selection highlight → ready | 221.5 / 252.4 |
| Export SVG | 303 / 308.4 |
| Export PNG | 614 / 690.7 |
| Retained JS heap per mount (MB) | 6.5 / 7.5 |
| Retained DOM nodes per mount | 10330 / 10330 |
| Leak check (after unmount + GC) | {"heapMBAfterUnmountVsBefore":1.5,"domNodesAfterUnmountVsBefore":0} |

**50,000 points**

| Metric | v0-plotly2.35.2-rp2.6.0 |
|---|---|
| Initial render → ready | 1383.6 / 1419 |
| Initial render → painted | 1603.4 / 1637.6 |
| Figure spec build | 111.1 / 114.7 |
| Filter update → ready | 740.6 / 1098.4 |
| Selection highlight → ready | 1058 / 1072.6 |
| Export SVG | 1610.4 / 1778.7 |
| Export PNG | 2984 / 3187 |
| Retained JS heap per mount (MB) | 31.4 / 31.7 |
| Retained DOM nodes per mount | 50330 / 50330 |
| Leak check (after unmount + GC) | {"heapMBAfterUnmountVsBefore":1.3,"domNodesAfterUnmountVsBefore":0} |

### Real FLEX data in the app, chromium: median / p95 ms

| Metric | v0-plotly2.35.2-rp2.6.0 |
|---|---|
| Cold load → shell | 90.7 / 98 |
| Cold load → first chart drawn | 410 / 422.9 |
| DOMContentLoaded | 45.8 / 50.5 |
| First contentful paint | 76 / 88 |
| View switch → chart | 20.7 / 31.7 |
| Filter toggle → chart | 14.4 / 17.5 |
| Selection → inspector open | 4.4 / 4.9 |
| Inspector close | 1.3 / 1.6 |
| CSV export (end-to-end) | 49.5 / 69 |
| SVG export (end-to-end) | 67 / 110 |
| PNG export (end-to-end) | 84.5 / 141 |
| Transferred (KB) / Plotly chunk (KB) | 613 / 463 |
| JS heap before → after 20 reps (MB) | 10.6 → 11.7 |


## Part 4 — Candidate results, decision and final stack (executed 2026-11-13)

All candidates used identical application code, the same tests and the same benchmark (Chromium = system Chrome, Windows 11, 12 logical CPUs; warm-up, repetitions, median / p95 as in Part 2; noise band about ±3–5 %, and the unchanged stack's own cold load drifted 410→433 ms across the day).

### 4.1 Gates per verified Cartesian candidate

| Candidate (engine / wrapper) | tsc app+tests | Vitest | e2e functional+integrity+visual | Bundle (Plotly chunk gzip KB, chunks) | Cloud default in bundle | Correctness verdict |
|---|---|---|---|---|---|---|
| 2.35.2 / 2.6.0 (original) | pass | pass | pass | 463, 1 | false | baseline |
| 3.7.0 / 4.1.0 | pass | pass | pass | 465 (the Plotly chunk grows more in raw size, see Part 1b) | false | pass |
| 4.1.2, 4.2.0, 4.3.0 / 4.1.0 | pass | pass | pass | 492–495 | **true** (neutralised by `showSendToCloud: false`) | pass |
| **2.35.3 / 2.6.0** | pass after a one-line types fix (`easing: 'linear'` beside `duration: 0`; no runtime effect) | 35/35 | 26/26 | 462, 1 | false | pass |

Cartesian 4.3.0 does exist (Part 1c). Full `plotly.js-dist-min` 4.3.0 was never substituted.

### 4.2 Performance (median / p95 ms, Chromium)

| Metric | 2.35.2 | **2.35.3** | 3.7.0 | 4.1.2 | 4.2.0 | 4.3.0 |
|---|---|---|---|---|---|---|
| Real data: cold load → first chart | 410 / 423 | **433 / 495** | 568 / 601 | 601 / 667 | 607 / 624 | 630 / 668 |
| Real data: view switch | 20.7 / 31.7 | 20.6 / 29.6 | 21.1 / 26.3 | 23.5 / 30.1 | 23.4 / 28.8 | 23.7 / 28.7 |
| Real data: filter toggle | 14.4 / 17.5 | 13.6 / 16.6 | 14.4 / 18.2 | 14.8 / 18.7 | 15.1 / 18.7 | 14.4 / 18.4 |
| Synthetic 10k: initial render | 305 / 339 | 346 / 402 | 285 / 294 | 449 / 467 | 456 / 480 | 450 / 482 |
| Synthetic 10k: filter update | 185 / 219 | 197 / 236 | 213 / 248 | 296 / 368 | 301 / 421 | 302 / 366 |
| Synthetic 10k: SVG export | 303 / 308 | 303 / 368 | 320 / 331 | 443 / 458 | 433 / 481 | 433 / 504 |
| Synthetic 10k: PNG export | 614 / 691 | 632 / 654 | 652 / 732 | 793 / 864 | 741 / 847 | 745 / 770 |
| Plotly chunk (KB transferred) | 463 | 463 | 465 | 492 | 495 | 495 |

Real-FLEX numbers and synthetic stress numbers are separate benchmark families; all values are in-page `performance.now()` measurements around actual rendering, not data-transformation timings. The 3.7.0 synthetic initial render is faster than 2.35 at 1k–50k points, but its real cold load is +32 % (about +140 ms) and its update and export paths are slower. Plotly 4.x is 40–60 % slower than 2.35 on synthetic render, update and export and about 45 % slower on real cold load. The engine, not the wrapper, causes the cold-load regression (engine-by-wrapper matrix, `mx*` result files).

### 4.3 Decision

Rule applied: newest verified Cartesian version that passes all correctness, compatibility and performance gates without losing required behaviour. **Selected: `plotly.js-cartesian-dist-min` 2.35.3 with `react-plotly.js` 2.6.0** (single engine through the `plotly.js` alias; `@types/plotly.js` 3.0.15 and `@types/react-plotly.js` 2.6.3 for types).

* 3.x and 4.x were rejected on measured cold-load and initial-render regressions (plus update and export for 4.x), not on correctness: all of them pass the functional suites.
* 2.35.3 differs from 2.35.2 only by "Set height and width on the `.plotly-container` div to 100%" (plotly.js #7314). Every measured metric is within the noise band (cold load 410→433 ms matches the same-stack drift recorded in Part 3).
* **Disclosure:** the gate written before the runs said "real-data interaction timings". On those alone 3.7.0 also passes, and the newest passing version would then be 3.7.0 or later. The task's own benchmark list also names initial chart rendering, so cold load and initial render were treated as gates. Reading the gate the narrower way flips the outcome to 3.7.0 (or the 4.x line if its cold-load and export costs are accepted), so this choice needs the reviewer's confirmation.
* Security was not a reason to move: no published advisory covers any compared version (Part 1c). The prototype-pollution item in 4.3.0 is a hardening fix with no CVE or GHSA.

### 4.4 Other stack decisions

* **Playwright** 1.65.0 and **@axe-core/playwright** 4.14.0: one `playwright-core` 1.65.0 in the tree (`npm ls` verified, deduped).
* **Single engine:** the full `plotly.js` peer is not installed; `node_modules/plotly.js` is the Cartesian build (2 MB). The built bundle has exactly one Plotly chunk, no non-Cartesian trace registration and no map JavaScript (`scripts/check-bundle.mjs`, positive-control validated against the full engine).
* **`showSendToCloud: false`** is explicit and tested (the toolbar has no cloud action).
* **TanStack Table:** V8 8.20.6 retained. V9.3.1 was **not** ported or measured in this session, so there is no measured benefit to justify migration under the pre-registered rule.
* **Vitest:** 3.0.5 retained. `npm audit` reports 3 advisories (1 moderate, 2 critical: Vitest UI-server file read, mocker, tinypool worker-options prototype pollution), all in the **dev-only** test runner; production dependencies audit at 0. The fix requires the Vitest 5 major. Not applied: the UI server is not used, no untrusted mocks or inputs are run, and a major runner migration is outside the safe-modernisation brief. A 3.2.7 patch bump was tried, did not clear the findings, and was reverted. Recommended as a separate, tested migration.
* **Install scripts (whole lock file, 169 packages):** only `esbuild@0.25.12` (`install.js`, platform-binary check; installs were run with `--ignore-scripts` and build and tests work) and `fsevents@2.3.3` (macOS-only, not installed on Windows). The 228-package full-Plotly tree, including its `es5-ext` postinstall, is gone. Production runtime packages: 12, all MIT. Licence census of the whole tree: MIT 153, Apache-2.0 6, ISC 6, MPL-2.0 2, BSD-3-Clause 1, CC-BY-4.0 1.

### 4.5 Browser coverage actually achieved

| Browser | Result |
|---|---|
| Chromium (system Chrome) | **52/52 passed**: lab sections, light and dark, desktop and 390 px mobile, selection and linked filtering, duplicate 193F001 identity, SVG/PNG export integrity, axe on every view, keyboard, reduced motion, 9 visual baselines, console-error scan |
| Firefox 159.0 | **Not completed.** After the approved download 2 axe tests passed; then Firefox crashed in its software compositor and `firefox.exe` disappeared. A reinstall failed with `EPERM` on `firefox.exe`. The remaining Firefox failures read "Executable doesn't exist" and say nothing about the application |
| WebKit 27.2 | **Not completed.** 3 axe tests passed, one then hung to the 90 s test timeout and `Playwright.exe` disappeared the same way |

The removal and blocking of freshly extracted unsigned browser binaries looks like endpoint protection on this machine. It was not worked around, and no security setting was changed. To finish cross-browser QA, run `E2E_BROWSERS=chromium,firefox,webkit npx playwright test --update-snapshots=missing` on a machine, or with a folder exclusion that the owner approves, where the Playwright browser cache is allowed. Firefox and WebKit visual baselines and benchmarks therefore do not exist yet, and no cross-browser pass is claimed. Browsers were installed to `D:\UnderFitted_FlameScope\.pw-browsers` because `C:` had under 0.5 GB free; that folder was deleted afterwards.

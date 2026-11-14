import { useEffect, useMemo, useState } from 'react';
import { api, loadOfflinePhysicsBaseline } from '../../api/client';
import type {
  D2ConsistencyResponse,
  D2RunResult,
  OxygenEffectResponse,
  OxygenStratumResult,
} from '../../api/contracts';
import { strataFor } from '../data/selectors';
import { FIELD_LABEL, SUPPORT_LABEL } from '../data/types';
import type { NumericField } from '../data/types';
import { useLab } from '../state/LabContext';

const ANALYSES = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6'] as const;
type AnalysisView = 'd2' | 'o2' | 'strata';
type FuelFilter = 'all' | 'Heptane' | 'Methanol';

function formatRho(value: number | null): string {
  return value === null ? 'Not reported (n < 5 or no variation)' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

function formatNum(value: number | null | undefined, decimals = 3): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatInterval(interval: [number, number] | null | undefined, decimals = 3): string {
  if (!interval) return '—';
  return `[${formatNum(interval[0], decimals)}, ${formatNum(interval[1], decimals)}]`;
}

export function AnalysisResults() {
  const { dataset, filters, select } = useLab();
  const [activeView, setActiveView] = useState<AnalysisView>('d2');

  // Physics data states
  const [d2Data, setD2Data] = useState<D2ConsistencyResponse | null>(null);
  const [o2Data, setO2Data] = useState<OxygenEffectResponse | null>(null);
  const [physicsLoading, setPhysicsLoading] = useState<boolean>(true);
  const [physicsSource, setPhysicsSource] = useState<'live' | 'offline_baseline'>('offline_baseline');
  const [physicsError, setPhysicsError] = useState<string | null>(null);

  // Diagnostic interactive filters
  const [d2Fuel, setD2Fuel] = useState<FuelFilter>('all');
  const [diameterHalfwidth, setDiameterHalfwidth] = useState<number>(0);
  const [o2Fuel, setO2Fuel] = useState<FuelFilter>('all');
  const [d2Search, setD2Search] = useState<string>('');
  const [showAllD2Runs, setShowAllD2Runs] = useState<boolean>(false);

  // Helper to open inspector by run ID
  const openRunInspector = (runId: string) => {
    const psiRow = parseInt(runId.replace(/^PSI-69-r/, ''), 10);
    const rec = dataset.records.find((r) => r.psi_row === psiRow);
    if (rec) select(rec.record_key);
  };

  // Fetch physics data: try live API first; fall back to verified baseline
  const fetchPhysics = async () => {
    setPhysicsLoading(true);
    setPhysicsError(null);
    try {
      const fuelParam = d2Fuel === 'all' ? undefined : d2Fuel;
      const hwParam = diameterHalfwidth > 0 ? diameterHalfwidth : undefined;
      const [d2, o2] = await Promise.all([
        api.getD2Consistency({ fuel: fuelParam, diameter_halfwidth_mm: hwParam }),
        api.getOxygenEffect({ fuel: o2Fuel === 'all' ? undefined : o2Fuel }),
      ]);
      setD2Data(d2);
      setO2Data(o2);
      setPhysicsSource('live');
    } catch {
      // Live API unreachable or returned 503; load verified offline baseline
      try {
        const baseline = await loadOfflinePhysicsBaseline();
        // Client-side filter if user selected a fuel for offline view
        let filteredD2 = baseline.d2_consistency;
        if (d2Fuel !== 'all') {
          filteredD2 = {
            ...filteredD2,
            runs: filteredD2.runs.filter((r) => r.fuel === d2Fuel),
            by_fuel: { [d2Fuel]: filteredD2.by_fuel[d2Fuel] },
            flagged_for_review: filteredD2.flagged_for_review.filter((id) =>
              filteredD2.runs.some((r) => r.run_id === id && r.fuel === d2Fuel),
            ),
          };
        }
        let filteredO2 = baseline.oxygen_effect;
        if (o2Fuel !== 'all') {
          filteredO2 = {
            ...filteredO2,
            strata: filteredO2.strata.filter((s) => s.fuel === o2Fuel),
          };
        }
        setD2Data(filteredD2);
        setO2Data(filteredO2);
        setPhysicsSource('offline_baseline');
      } catch (err: unknown) {
        setPhysicsError(err instanceof Error ? err.message : 'Failed to load physics data');
      }
    } finally {
      setPhysicsLoading(false);
    }
  };

  useEffect(() => {
    void fetchPhysics();
  }, [d2Fuel, diameterHalfwidth, o2Fuel]);

  // Baseline published analysis calculations
  const analyses = ANALYSES.map((analysis) => ({
    analysis,
    rows: strataFor(dataset, analysis, filters.supportModes, filters.fuels),
  }));
  const visiblePublished = analyses.filter(({ rows }) => rows.length > 0);

  // Filtered runs for d2 table
  const filteredD2Runs = useMemo(() => {
    if (!d2Data) return [];
    const term = d2Search.trim().toLowerCase();
    if (!term) return d2Data.runs;
    return d2Data.runs.filter(
      (r) =>
        r.run_id.toLowerCase().includes(term) ||
        r.experiment_id.toLowerCase().includes(term) ||
        r.fuel.toLowerCase().includes(term),
    );
  }, [d2Data, d2Search]);

  const flaggedRuns = useMemo(() => {
    if (!d2Data) return [];
    return d2Data.runs.filter((r) => d2Data.flagged_for_review.includes(r.run_id));
  }, [d2Data]);

  return (
    <div className="stack">
      <section className="card" aria-labelledby="analysis-main-title">
        <header className="card-head">
          <div className="explorer-heading">
            <div>
              <span className="eyebrow">FlameScope Scientific Analysis · PSI-69 FLEX Evidence</span>
              <h2 id="analysis-main-title">Combustion Physics & Published Results</h2>
              <p className="question">
                Explore physics-informed diagnostics ($d^2$-law internal consistency), regression models (ambient
                oxygen effect on burning rates with robust HC3 inference), and published correlation strata.
              </p>
            </div>
            <div className="status-badges">
              {physicsSource === 'live' ? (
                <span className="explorer-status status-verified" title="Results generated live by FastAPI backend">
                  ● Live Physics API
                </span>
              ) : (
                <span
                  className="explorer-status"
                  title="Results loaded from verified precomputed baseline v0.1.1 (SHA-256 verified)"
                >
                  Verified Baseline v0.1.1
                </span>
              )}
            </div>
          </div>
        </header>

        {/* View switcher tabs */}
        <div className="subnav" role="tablist" aria-label="Analysis perspectives">
          <button
            type="button"
            role="tab"
            aria-selected={activeView === 'd2'}
            className={`subnav-tab ${activeView === 'd2' ? 'active' : ''}`}
            onClick={() => setActiveView('d2')}
          >
            d²-Law Consistency (Diagnostic)
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeView === 'o2'}
            className={`subnav-tab ${activeView === 'o2' ? 'active' : ''}`}
            onClick={() => setActiveView('o2')}
          >
            Oxygen Effect on K (OLS / HC3)
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeView === 'strata'}
            className={`subnav-tab ${activeView === 'strata' ? 'active' : ''}`}
            onClick={() => setActiveView('strata')}
          >
            Published Correlation Strata (v0.2.0)
          </button>
        </div>

        {/* SECTION 1: d^2-Law Internal Consistency */}
        {activeView === 'd2' && (
          <div className="physics-section" role="tabpanel" aria-label="d²-law consistency">
            <div className="callout" role="note">
              <strong>Physics Diagnostic Contract.</strong> Tests the internal consistency of NASA-reported{' '}
              <code>D₀</code>, <code>D_ext</code>, burning-rate constant <code>K</code>, and burn time{' '}
              <code>t_burn</code> with the classical $d^2$-law:
              <p className="formula" style={{ margin: '6px 0' }}>
                <code>t_d2 = (D₀² - D_ext²) / K ;  r = t_d2 / t_burn  (from D(t)² = D₀² - K·t)</code>
              </p>
              This is a <em>data-quality screening diagnostic</em>, not a physical validation of the $d^2$-law.
              Because reported $K$ excludes the heat-up transient and burn-time definitions are undocumented,{' '}
              $r = 1.0$ is not expected. Runs far from their fuel's typical ratio are flagged for investigator review,
              never silently altered or discarded.
            </div>

            {/* Diagnostic controls */}
            <div className="filter-controls-row">
              <label>
                <span>Filter Fuel:</span>
                <select
                  value={d2Fuel}
                  onChange={(e) => setD2Fuel(e.target.value as FuelFilter)}
                  aria-label="Filter fuel for d2 consistency"
                >
                  <option value="all">All Fuels (154 evaluated extinction runs)</option>
                  <option value="Heptane">Heptane only (54 runs)</option>
                  <option value="Methanol">Methanol only (100 runs)</option>
                </select>
              </label>

              <label>
                <span>Diameter Uncertainty Bound (± mm):</span>
                <input
                  type="number"
                  min="0"
                  max="1.0"
                  step="0.01"
                  value={diameterHalfwidth}
                  onChange={(e) => setDiameterHalfwidth(parseFloat(e.target.value) || 0)}
                  placeholder="0.00"
                  aria-label="Additional diameter uncertainty bound in millimeters"
                />
              </label>

              <button
                type="button"
                className="ghost"
                onClick={fetchPhysics}
                disabled={physicsLoading}
                aria-label="Recalculate d2 consistency"
              >
                {physicsLoading ? 'Evaluating…' : '↻ Recalculate'}
              </button>
            </div>

            {physicsLoading && !d2Data && (
              <div className="explorer-skeleton">
                <span />
                <span />
                <span />
              </div>
            )}

            {physicsError && (
              <div className="explorer-error" role="alert">
                <p>
                  <strong>Physics evaluation error:</strong> {physicsError}
                </p>
              </div>
            )}

            {d2Data && (
              <>
                {/* Summary stat cards */}
                <div className="physics-grid">
                  {Object.entries(d2Data.by_fuel).map(([fuel, s]) => (
                    <div className="card physics-card" key={fuel}>
                      <div className="card-head">
                        <span className="eyebrow">{fuel} Fuel</span>
                        <h3>
                          Median r = {formatNum(s.median, 3)}{' '}
                          <span className="small muted">
                            (95% CI: {formatInterval(s.median_ci95, 3)})
                          </span>
                        </h3>
                      </div>
                      <dl className="kv" style={{ margin: '8px 0' }}>
                        <div>
                          <dt>Evaluated runs (n)</dt>
                          <dd>
                            <strong>{s.n}</strong> extinction runs
                          </dd>
                        </div>
                        <div>
                          <dt>Interquartile range [Q₁, Q₃]</dt>
                          <dd>
                            [{formatNum(s.q1, 3)}, {formatNum(s.q3, 3)}] (IQR ={' '}
                            {formatNum(s.q3 - s.q1, 3)})
                          </dd>
                        </div>
                        <div>
                          <dt>Tukey fences (1.5 × IQR)</dt>
                          <dd>
                            [{formatNum(s.tukey_fences[0], 3)}, {formatNum(s.tukey_fences[1], 3)}]
                          </dd>
                        </div>
                        <div>
                          <dt>Interval covers r = 1.0</dt>
                          <dd>
                            <strong>{(s.share_of_intervals_containing_1 * 100).toFixed(1)}%</strong> of runs
                          </dd>
                        </div>
                        <div>
                          <dt>Observed range [Min, Max]</dt>
                          <dd>
                            [{formatNum(s.min, 3)}, {formatNum(s.max, 3)}]
                          </dd>
                        </div>
                      </dl>
                      <p className="small muted">
                        Median uncertainty: {d2Data.uncertainty.summary}. Interval: {d2Data.uncertainty.per_run}.
                      </p>
                    </div>
                  ))}

                  {/* Exclusions card */}
                  <div className="card physics-card">
                    <div className="card-head">
                      <span className="eyebrow">PSI-69 Table Usability</span>
                      <h3>Usable: {d2Data.n_runs} / 274 Runs</h3>
                    </div>
                    <p className="small muted">
                      Runs excluded from the $d^2$ diagnostic by strict NASA data verification rules:
                    </p>
                    <ul className="exclusion-list">
                      {Object.entries(d2Data.excluded).map(([reason, count]) => (
                        <li key={reason}>
                          <span className="tag warn">{count}</span> {reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Flagged Runs for Review */}
                <section className="flagged-section" aria-labelledby="flagged-runs-title">
                  <div className="explorer-heading">
                    <div>
                      <h3 id="flagged-runs-title">
                        Flagged Runs for Review ({flaggedRuns.length} runs)
                      </h3>
                      <p className="small muted">
                        Runs whose entire resolution interval lies outside the fuel Tukey fences. These are
                        prioritized for visual/caption inspection, not discarded.
                      </p>
                    </div>
                    <span className="tag warn">{flaggedRuns.length} flagged</span>
                  </div>

                  {flaggedRuns.length === 0 ? (
                    <p className="explorer-state">
                      No runs are flagged for review under the selected uncertainty parameters.
                    </p>
                  ) : (
                    <div className="table-scroll">
                      <table className="data">
                        <thead>
                          <tr>
                            <th scope="col">Run ID</th>
                            <th scope="col">FLEX Test</th>
                            <th scope="col">Fuel</th>
                            <th scope="col">D₀ (mm)</th>
                            <th scope="col">D_ext (mm)</th>
                            <th scope="col">K (mm²/s)</th>
                            <th scope="col">t_burn (s)</th>
                            <th scope="col">t_d2 (s)</th>
                            <th scope="col">Ratio r</th>
                            <th scope="col">Resolution Interval</th>
                            <th scope="col">Review Flag</th>
                          </tr>
                        </thead>
                        <tbody>
                          {flaggedRuns.map((r) => (
                            <tr key={r.run_id}>
                              <th scope="row">
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() => openRunInspector(r.run_id)}
                                  aria-label={`Inspect evidence for ${r.run_id}`}
                                >
                                  {r.run_id}
                                </button>
                              </th>
                              <td>{r.experiment_id}</td>
                              <td>{r.fuel}</td>
                              <td className="num">{formatNum(r.d0_mm, 2)}</td>
                              <td className="num">{formatNum(r.dext_mm, 2)}</td>
                              <td className="num">{formatNum(r.k_mm2_s, 3)}</td>
                              <td className="num">{formatNum(r.burn_time_s, 2)}</td>
                              <td className="num">{formatNum(r.t_d2_s, 2)}</td>
                              <td className="num">
                                <strong>{formatNum(r.ratio, 3)}</strong>
                              </td>
                              <td className="num">{formatInterval(r.ratio_interval, 3)}</td>
                              <td>
                                <span className="tag warn">{r.review_flag}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>

                {/* All Evaluated Runs Table (Collapsible) */}
                <section className="all-runs-section" aria-labelledby="all-evaluated-runs-title">
                  <div className="explorer-heading">
                    <div>
                      <h3 id="all-evaluated-runs-title">
                        All Evaluated Runs ({filteredD2Runs.length} matching)
                      </h3>
                      <p className="small muted">
                        Search and inspect all usable extinction runs and their computed $d^2$-law consistency.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="ghost small"
                      onClick={() => setShowAllD2Runs(!showAllD2Runs)}
                    >
                      {showAllD2Runs ? '▲ Collapse Table' : '▼ Expand Full Table'}
                    </button>
                  </div>

                  {showAllD2Runs && (
                    <>
                      <div className="explorer-search" style={{ margin: '8px 0' }}>
                        <input
                          type="search"
                          placeholder="Search run ID, test number, or fuel..."
                          value={d2Search}
                          onChange={(e) => setD2Search(e.target.value)}
                        />
                      </div>
                      <div className="table-scroll" style={{ maxHeight: '50vh' }}>
                        <table className="data">
                          <thead>
                            <tr>
                              <th scope="col">Run ID</th>
                              <th scope="col">FLEX Test</th>
                              <th scope="col">Fuel</th>
                              <th scope="col">D₀ (mm)</th>
                              <th scope="col">D_ext (mm)</th>
                              <th scope="col">K (mm²/s)</th>
                              <th scope="col">t_burn (s)</th>
                              <th scope="col">t_d2 (s)</th>
                              <th scope="col">Ratio r</th>
                              <th scope="col">Resolution Interval</th>
                              <th scope="col">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filteredD2Runs.slice(0, 100).map((r) => (
                              <tr key={r.run_id}>
                                <th scope="row">
                                  <button
                                    type="button"
                                    className="text-button"
                                    onClick={() => openRunInspector(r.run_id)}
                                  >
                                    {r.run_id}
                                  </button>
                                </th>
                                <td>{r.experiment_id}</td>
                                <td>{r.fuel}</td>
                                <td className="num">{formatNum(r.d0_mm, 2)}</td>
                                <td className="num">{formatNum(r.dext_mm, 2)}</td>
                                <td className="num">{formatNum(r.k_mm2_s, 3)}</td>
                                <td className="num">{formatNum(r.burn_time_s, 2)}</td>
                                <td className="num">{formatNum(r.t_d2_s, 2)}</td>
                                <td className="num">{formatNum(r.ratio, 3)}</td>
                                <td className="num">{formatInterval(r.ratio_interval, 3)}</td>
                                <td>
                                  {r.review_flag ? (
                                    <span className="tag warn">Review</span>
                                  ) : (
                                    <span className="tag ok">Within Fences</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </section>

                {/* Limitations */}
                <div className="callout" role="note" style={{ marginTop: '16px' }}>
                  <strong>Scientific Limitations & Governance:</strong>
                  <ul>
                    {d2Data.limitations.map((lim, idx) => (
                      <li key={idx}>{lim}</li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>
        )}

        {/* SECTION 2: Oxygen Effect on Reported Burning Rate K */}
        {activeView === 'o2' && (
          <div className="physics-section" role="tabpanel" aria-label="Oxygen effect regression">
            <div className="callout" role="note">
              <strong>Within-Stratum OLS Regression Contract.</strong> Examines the linear association between
              ambient oxygen mole fraction X_O₂ and the reported burning rate constant K holding diluent
              (N₂-only), pressure cluster, and droplet support mode strictly fixed:
              <p className="formula" style={{ margin: '6px 0' }}>
                <code>K = b₀ + b₁·X_O₂  (sensitivity check: + b₂·D₀) ; OLS with HC3 robust standard errors</code>
              </p>
              Heteroskedasticity-consistent standard errors (HC3) and Student-t 95% confidence intervals are used
              to prevent anti-conservative inference in small experimental strata.
            </div>

            {/* Filter controls */}
            <div className="filter-controls-row">
              <label>
                <span>Filter Fuel:</span>
                <select
                  value={o2Fuel}
                  onChange={(e) => setO2Fuel(e.target.value as FuelFilter)}
                  aria-label="Filter fuel for oxygen effect"
                >
                  <option value="all">All Fuels (11 strata evaluated)</option>
                  <option value="Heptane">Heptane only</option>
                  <option value="Methanol">Methanol only</option>
                </select>
              </label>

              <button
                type="button"
                className="ghost"
                onClick={fetchPhysics}
                disabled={physicsLoading}
                aria-label="Refresh oxygen effect regression"
              >
                {physicsLoading ? 'Evaluating…' : '↻ Refresh Regression'}
              </button>
            </div>

            {physicsLoading && !o2Data && (
              <div className="explorer-skeleton">
                <span />
                <span />
                <span />
              </div>
            )}

            {o2Data && (
              <>
                {/* Computable Strata Cards */}
                <section aria-labelledby="computable-strata-title">
                  <div className="explorer-heading">
                    <div>
                      <h3 id="computable-strata-title">
                        Computable Experimental Strata (
                        {o2Data.strata.filter((s) => s.computable).length} strata satisfy n ≥ 8 and ≥ 3 O₂
                        levels)
                      </h3>
                      <p className="small muted">
                        Strata where sample size and compositional variation justify linear modeling without pooling.
                      </p>
                    </div>
                  </div>

                  <div className="physics-grid">
                    {o2Data.strata
                      .filter((s) => s.computable)
                      .map((s, idx) => {
                        const m = s.model_k_on_o2;
                        const sens = s.sensitivity_k_on_o2_and_d0;
                        return (
                          <div className="card physics-card" key={`${s.fuel}-${s.support_mode}-${idx}`}>
                            <div className="card-head">
                              <span className="eyebrow">
                                {s.fuel} · {s.pressure_cluster ?? 'unclustered pressure'} ·{' '}
                                {SUPPORT_LABEL[s.support_mode as keyof typeof SUPPORT_LABEL] ?? s.support_mode}
                              </span>
                              <h3>
                                Slope b₁ = +{formatNum(m?.x_o2.estimate, 2)}{' '}
                                <span className="small muted">mm²/s per unit X_O₂</span>
                              </h3>
                            </div>

                            <dl className="kv" style={{ margin: '8px 0' }}>
                              <div>
                                <dt>Sample size (n)</dt>
                                <dd>
                                  <strong>{s.n}</strong> tests across {s.n_distinct_o2} distinct O₂ levels
                                </dd>
                              </div>
                              <div>
                                <dt>O₂ mole fraction range</dt>
                                <dd>{formatInterval(s.x_o2_range, 2)}</dd>
                              </div>
                              <div>
                                <dt>Slope 95% CI (Student-t)</dt>
                                <dd>
                                  <strong>{formatInterval(m?.x_o2.ci95, 2)}</strong> (HC3 SE ={' '}
                                  {formatNum(m?.x_o2.se_hc3, 3)})
                                </dd>
                              </div>
                              <div>
                                <dt>Statistical significance</dt>
                                <dd>
                                  p = {m?.x_o2.p_value ? m.x_o2.p_value.toExponential(3) : '—'} · R² ={' '}
                                  {formatNum(m?.r_squared, 3)}
                                </dd>
                              </div>
                              <div>
                                <dt>Intercept b₀</dt>
                                <dd>
                                  {formatNum(m?.intercept.estimate, 3)} (95% CI:{' '}
                                  {formatInterval(m?.intercept.ci95, 3)}, p ={' '}
                                  {formatNum(m?.intercept.p_value, 3)})
                                </dd>
                              </div>
                              <div>
                                <dt>D₀-Adjusted Slope (Sensitivity)</dt>
                                <dd>
                                  {sens ? (
                                    <>
                                      b₁ = +{formatNum(sens.x_o2.estimate, 2)} (p ={' '}
                                      {sens.x_o2.p_value.toExponential(2)}) ; b₂(D₀) ={' '}
                                      {formatNum(sens.d0_mm?.estimate, 4)}
                                    </>
                                  ) : (
                                    'n < 10 (sensitivity model abstained)'
                                  )}
                                </dd>
                              </div>
                              <div>
                                <dt>Nonparametric Spearman ρ</dt>
                                <dd>{formatRho(s.spearman_o2_k ?? null)}</dd>
                              </div>
                            </dl>

                            <details style={{ marginTop: '10px', fontSize: '12px' }}>
                              <summary>View {s.run_ids.length} included test runs</summary>
                              <div className="explorer-chips" style={{ marginTop: '6px' }}>
                                {s.run_ids.map((id) => (
                                  <button
                                    key={id}
                                    type="button"
                                    className="text-button small"
                                    onClick={() => openRunInspector(id)}
                                  >
                                    {id}
                                  </button>
                                ))}
                              </div>
                            </details>
                          </div>
                        );
                      })}
                  </div>
                </section>

                {/* Abstained Strata (Scientific Rigor) */}
                <section
                  className="abstained-section"
                  aria-labelledby="abstained-strata-title"
                  style={{ marginTop: '20px' }}
                >
                  <div className="explorer-heading">
                    <div>
                      <h3 id="abstained-strata-title">
                        Abstained Strata ({o2Data.strata.filter((s) => !s.computable).length} strata not
                        computed)
                      </h3>
                      <p className="small muted">
                        Strata with small sample size ($n &lt; 8$) or narrow oxygen variation (&lt; 3 distinct
                        levels). These are abstained to prevent misleading regressions.
                      </p>
                    </div>
                  </div>

                  <div className="table-scroll">
                    <table className="data">
                      <thead>
                        <tr>
                          <th scope="col">Fuel</th>
                          <th scope="col">Pressure Cluster</th>
                          <th scope="col">Support Mode</th>
                          <th scope="col">n</th>
                          <th scope="col">Distinct O₂</th>
                          <th scope="col">O₂ Range</th>
                          <th scope="col">Abstention Reason</th>
                          <th scope="col">Included Runs</th>
                        </tr>
                      </thead>
                      <tbody>
                        {o2Data.strata
                          .filter((s) => !s.computable)
                          .map((s, idx) => (
                            <tr key={`${s.fuel}-${idx}`}>
                              <td>{s.fuel}</td>
                              <td>{s.pressure_cluster ?? 'unclustered'}</td>
                              <td>
                                {SUPPORT_LABEL[s.support_mode as keyof typeof SUPPORT_LABEL] ??
                                  s.support_mode}
                              </td>
                              <td className="num">{s.n}</td>
                              <td className="num">{s.n_distinct_o2}</td>
                              <td>{formatInterval(s.x_o2_range, 2)}</td>
                              <td>
                                <span className="tag warn">{s.abstention_reason}</span>
                              </td>
                              <td>
                                {s.run_ids.slice(0, 4).map((id, i) => (
                                  <span key={id}>
                                    {i > 0 ? ', ' : ''}
                                    <button
                                      type="button"
                                      className="text-button"
                                      onClick={() => openRunInspector(id)}
                                    >
                                      {id}
                                    </button>
                                  </span>
                                ))}
                                {s.run_ids.length > 4 && ` +${s.run_ids.length - 4} more`}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {/* Limitations */}
                <div className="callout" role="note" style={{ marginTop: '16px' }}>
                  <strong>Scientific Limitations & Governance:</strong>
                  <ul>
                    {o2Data.limitations.map((lim, idx) => (
                      <li key={idx}>{lim}</li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>
        )}

        {/* SECTION 3: Published Correlation Strata (v0.2.0 Baseline) */}
        {activeView === 'strata' && (
          <div className="published-section" role="tabpanel" aria-label="Published correlation strata">
            <div className="callout" role="note">
              <strong>Interpretation limits.</strong> ρ is descriptive; no p-values or multiple-comparison
              correction are supplied. A missing ρ means n &lt; 5 or no variation. The reported burning-rate
              constant has no uncertainty in this dataset. Results describe observational test strata and do not
              establish causation.
            </div>

            {visiblePublished.length === 0 ? (
              <p className="explorer-state">No analysis strata match the selected fuels and support modes.</p>
            ) : (
              visiblePublished.map(({ analysis, rows }) => (
                <section
                  className="analysis-result-group"
                  key={analysis}
                  aria-labelledby={`analysis-${analysis}`}
                >
                  <h3 id={`analysis-${analysis}`}>
                    {analysis} <span className="small muted">{rows.length} matching strata</span>
                  </h3>
                  <div className="table-scroll">
                    <table className="data">
                      <thead>
                        <tr>
                          <th scope="col">Fuel</th>
                          <th scope="col">Support</th>
                          <th scope="col">Variables</th>
                          <th scope="col">Stratum conditions</th>
                          <th scope="col">n</th>
                          <th scope="col">Spearman ρ</th>
                          <th scope="col">Sensitivity</th>
                          <th scope="col">Source PSI rows</th>
                          <th scope="col">Analysis note</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, index) => (
                          <tr key={`${row.analysis}-${row.fuel}-${index}`}>
                            <td>{row.fuel}</td>
                            <td>
                              {SUPPORT_LABEL[String(row.stratum.support_mode) as keyof typeof SUPPORT_LABEL] ??
                                String(row.stratum.support_mode)}
                            </td>
                            <td>
                              {[row.x, row.y]
                                .map((field) =>
                                  field in FIELD_LABEL
                                    ? `${FIELD_LABEL[field as NumericField]} (${
                                        dataset.units[field as NumericField]
                                      })`
                                    : field,
                                )
                                .join(' → ')}
                            </td>
                            <td>
                              {Object.entries(row.stratum)
                                .filter(([key]) => key !== 'support_mode')
                                .map(([key, value]) => `${key}=${value ?? 'unknown'}`)
                                .join('; ') || '—'}
                            </td>
                            <td className="num">{row.n}</td>
                            <td className="num">{formatRho(row.rho_spearman)}</td>
                            <td>
                              {row.sensitivity_rows.length
                                ? `PSI ${row.sensitivity_rows.join(', ')}; ρ without rows: ${formatRho(
                                    row.rho_without_sensitivity_rows,
                                  )}`
                                : 'No tagged sensitivity rows'}
                            </td>
                            <td>
                              {row.psi_rows.map((psiRow, i) => {
                                const record = dataset.records.find((item) => item.psi_row === psiRow);
                                return (
                                  <span key={psiRow}>
                                    {i > 0 ? ', ' : ''}
                                    {record ? (
                                      <button
                                        className="text-button"
                                        type="button"
                                        onClick={() => select(record.record_key)}
                                        aria-label={`Inspect PSI row ${psiRow} evidence`}
                                      >
                                        {psiRow}
                                      </button>
                                    ) : (
                                      psiRow
                                    )}
                                  </span>
                                );
                              })}
                            </td>
                            <td className="small">{row.note}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ))
            )}
          </div>
        )}

        <footer style={{ marginTop: '20px' }}>
          <p className="small muted">
            Source: NASA PSI-69, DOI{' '}
            <a href={`https://doi.org/${dataset.provenance.doi}`} target="_blank" rel="noreferrer">
              {dataset.provenance.doi}
            </a>
            ; supporting report{' '}
            <a href={dataset.provenance.report_url} target="_blank" rel="noreferrer">
              NASA/TP-2015-216046
            </a>
            . PSI row and test numbers open their evidence inspector.
          </p>
        </footer>
      </section>
    </div>
  );
}

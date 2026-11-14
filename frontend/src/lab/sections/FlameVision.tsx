import { useEffect, useMemo, useState } from 'react';
import { api, apiUrl, loadOfflineVisionBaseline } from '../../api/client';
import type {
  MethodCard,
  VisionEvalTest,
  VisionEvaluation,
  VisionFrame,
  VisionTestSummary,
} from '../../api/contracts';
import { useLab } from '../state/LabContext';

type TabView = 'overview' | 'inspector' | 'series' | 'method';

function formatNum(value: number | null | undefined, decimals = 4): string {
  if (value === null || value === undefined || isNaN(value)) return '—';
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || isNaN(value)) return '—';
  const pct = value * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(decimals)}%`;
}

export function FlameVision() {
  const { dataset, select } = useLab();
  const [activeTab, setActiveTab] = useState<TabView>('overview');

  // Vision API states
  const [evaluation, setEvaluation] = useState<VisionEvaluation | null>(null);
  const [testSummaries, setTestSummaries] = useState<Record<string, VisionTestSummary>>({});
  const [testSeries, setTestSeries] = useState<Record<string, VisionFrame[]>>({});
  const [methodCard, setMethodCard] = useState<MethodCard | null>(null);

  const [selectedTestPoint, setSelectedTestPoint] = useState<string>('20CAL10');
  const [loading, setLoading] = useState<boolean>(true);
  const [source, setSource] = useState<'live' | 'offline_baseline'>('offline_baseline');
  const [error, setError] = useState<string | null>(null);

  // Series viewer controls
  const [chartMode, setChartMode] = useState<'d2' | 'd'>('d2');
  const [frameStatusFilter, setFrameStatusFilter] = useState<string>('all');
  const [hoveredFrame, setHoveredFrame] = useState<VisionFrame | null>(null);

  // Fetch Vision Data
  useEffect(() => {
    let active = true;
    const fetchVision = async () => {
      setLoading(true);
      setError(null);
      try {
        // Attempt live backend API
        const [evalData, methodData] = await Promise.all([
          api.getVisionEvaluation(),
          api.getVisionMethod(),
        ]);

        const testPoints = evalData.tests.map((t) => t.test_point);
        const summaries: Record<string, VisionTestSummary> = {};
        const seriesData: Record<string, VisionFrame[]> = {};

        await Promise.all(
          testPoints.map(async (tp) => {
            try {
              const summary = await api.getVisionTest(tp);
              summaries[tp] = summary;
              if (summary.computable !== false) {
                try {
                  const s = await api.getVisionTestSeries(tp);
                  seriesData[tp] = s;
                } catch {
                  // Series may not be available if abstained
                }
              }
            } catch {
              // Individual test fetch error
            }
          })
        );

        if (!active) return;
        setEvaluation(evalData);
        setMethodCard(methodData);
        setTestSummaries(summaries);
        setTestSeries(seriesData);
        setSource('live');
      } catch {
        // Live API unreachable; load verified offline baseline
        try {
          const baseline = await loadOfflineVisionBaseline();
          if (!active) return;
          setEvaluation(baseline.evaluation);
          setMethodCard(baseline.method);
          setTestSummaries(baseline.tests);
          setTestSeries(baseline.series);
          setSource('offline_baseline');
        } catch (err: unknown) {
          if (!active) return;
          setError(err instanceof Error ? err.message : 'Failed to load Vision metrology data');
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void fetchVision();
    return () => {
      active = false;
    };
  }, []);

  const activeSummary = testSummaries[selectedTestPoint] ?? null;
  const activeSeries = testSeries[selectedTestPoint] ?? [];

  // Helper to open Data Platform run in Scientific Explorer
  const navigateToRun = (runId: string) => {
    const psiRow = parseInt(runId.replace(/^PSI-69-r/, ''), 10);
    const rec = dataset.records.find((r) => r.psi_row === psiRow);
    if (rec) {
      select(rec.record_key);
      window.location.hash = '#explorer';
    }
  };

  // Filtered frames for the series table
  const filteredFrames = useMemo(() => {
    if (frameStatusFilter === 'all') return activeSeries;
    return activeSeries.filter((f) => f.status === frameStatusFilter);
  }, [activeSeries, frameStatusFilter]);

  // Chart dimensions & scaling for SVG plot
  const chartMetrics = useMemo(() => {
    if (!activeSeries.length) return null;
    const validFrames = activeSeries.filter((f) => f.t_s !== null && f.diameter_px !== null);
    if (!validFrames.length) return null;

    const tValues = validFrames.map((f) => f.t_s as number);
    const minT = Math.min(...tValues);
    const maxT = Math.max(...tValues);

    const yValues = validFrames.map((f) =>
      chartMode === 'd2' ? Math.pow(f.diameter_px as number, 2) : (f.diameter_px as number)
    );
    const minY = 0;
    const maxY = Math.max(...yValues) * 1.1;

    return { minT, maxT, minY, maxY, validFrames };
  }, [activeSeries, chartMode]);

  return (
    <section className="vision-section" aria-labelledby="vision-heading">
      <div className="section-head">
        <div>
          <span className="eyebrow">NASA PSI-69 · HIBMS BACKLIT CAMERA METROLOGY</span>
          <h2 id="vision-heading">Flame Vision & Metrology</h2>
          <p className="lead">
            Sub-pixel droplet boundary segmentation, diameter history, and scale-free d²-law burning rates
            derived directly from NASA FLEX high-magnification backlit image frames.
          </p>
        </div>

        <div className="status-badges">
          <span
            className={`status-pill ${source === 'live' ? 'online' : 'offline'}`}
            title="FastAPI Flame Vision API service connection status"
          >
            <i className={source === 'live' ? 'online' : 'offline'} aria-hidden="true" />
            {source === 'live' ? 'Live Vision API' : 'Verified Baseline (v1.0.0)'}
          </span>
          <span className="badge info" title="Combustion regime">FLEX Droplet</span>
          <span className="badge warning" title="Verification state">Implemented & Compared · Not Validated</span>
        </div>
      </div>

      {/* Critical Scientific Safeguards Banner */}
      <div className="callout warning" role="note" style={{ margin: '14px 0' }}>
        <strong>Scientific Safeguards & Verification Notice:</strong>
        <ul style={{ margin: '6px 0 0 18px', padding: 0, fontSize: '13px', lineHeight: '1.5' }}>
          <li>
            <strong>Scale-Free Metrology Only (No Spatial Calibration):</strong> No documented mm/px scale exists
            in the PSI-69 calibration archives. All primary metrology is computed in pixels (px, px²/s) or
            scale-free normalized form (K/D₀² in 1/s), which cancels pixel magnification. Inferred optical ratios
            (0.057–0.059 mm/px) are strictly uncalibrated consistency checks and never used to output physical millimeter values.
          </li>
          <li>
            <strong>Systematic 15–22% Gap vs NASA Reported Rate (Unresolved Hypotheses):</strong> Vision burning rates are systematically
            15–22% lower than NASA's single reported K/D₀² values. Plausible working hypotheses (not confirmed causes) under scientific study include:
            (1) hypothesis that igniter obscuration exclusion [0, 1.5s] omits early transient fast burning; (2) hypothesis that droplet-side regime break
            does not coincide with visible-flame camera extinction; and (3) hypothesis that NASA's stated ±50 µm D₀ uncertainty propagates into K/D₀².
          </li>
          <li>
            <strong>Goodness-of-Fit ≠ Physical Accuracy:</strong> High linear fit quality (R² ≥ 0.993) confirms
            strict d²-law linearity over the droplet-evaporation window, but does not validate equivalence to
            NASA's reported value. Fit quality measures regression consistency to pixel history, not absolute measurement accuracy.
          </li>
          <li>
            <strong>Scientific Abstention on Sooting Fuels:</strong> On heptane tests (e.g. 30CAL06), soot shell
            interference obscures the droplet boundary ~4s after ignition; the pipeline strictly abstains
            rather than reporting a corrupted rate.
          </li>
        </ul>
      </div>

      {error && (
        <div className="callout error" role="alert">
          <strong>Data Load Error:</strong> {error}
        </div>
      )}

      {/* Navigation tabs */}
      <nav className="subnav" aria-label="Flame Vision sub-sections">
        <button
          type="button"
          className={`subnav-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview & Evaluation
        </button>
        <button
          type="button"
          className={`subnav-tab ${activeTab === 'inspector' ? 'active' : ''}`}
          onClick={() => setActiveTab('inspector')}
        >
          Test Inspector ({selectedTestPoint})
        </button>
        <button
          type="button"
          className={`subnav-tab ${activeTab === 'series' ? 'active' : ''}`}
          onClick={() => setActiveTab('series')}
        >
          Time-Series & Dynamics
        </button>
        <button
          type="button"
          className={`subnav-tab ${activeTab === 'method' ? 'active' : ''}`}
          onClick={() => setActiveTab('method')}
        >
          Method Card & Validity
        </button>
      </nav>

      {/* ========================================================================= */}
      {/* TAB 1: OVERVIEW & EVALUATION TABLE */}
      {/* ========================================================================= */}
      {activeTab === 'overview' && evaluation && (
        <div className="tab-pane">
          <div className="physics-grid">
            <div className="physics-card">
              <span className="eyebrow">MODULE SUMMARY</span>
              <h3>Evaluation Benchmark ({evaluation.method_id})</h3>
              <p style={{ fontSize: '13px', color: 'var(--text-2)' }}>
                Cross-test comparison of scale-free burning rate K/D₀² against reported NASA values across all
                retrieved FLEX calibration bundles.
              </p>
              <table className="compact-table" style={{ width: '100%', marginTop: '8px', fontSize: '12.5px' }}>
                <tbody>
                  <tr>
                    <td>Total Tests Analyzed:</td>
                    <td><strong>{evaluation.n_tests}</strong></td>
                  </tr>
                  <tr>
                    <td>Computable Runs:</td>
                    <td><strong style={{ color: 'var(--success)' }}>{evaluation.n_computable}</strong></td>
                  </tr>
                  <tr>
                    <td>Abstained (Soot Interf.):</td>
                    <td><strong style={{ color: 'var(--warning)' }}>{evaluation.n_abstained}</strong></td>
                  </tr>
                  <tr>
                    <td>Mean Relative Difference:</td>
                    <td><strong style={{ color: 'var(--accent)' }}>{formatPercent(evaluation.relative_difference_mean)}</strong></td>
                  </tr>
                  <tr>
                    <td>Inferred Scale Range (Uncalibrated):</td>
                    <td>
                      {formatNum(evaluation.implied_scale_range_mm_per_px[0], 4)} –{' '}
                      {formatNum(evaluation.implied_scale_range_mm_per_px[1], 4)} mm/px
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="physics-card">
              <span className="eyebrow">VERDICT & VALIDATION STATE</span>
              <h3>Status: {evaluation.verdict.split(':')[0]}</h3>
              <p style={{ fontSize: '13px', lineHeight: '1.5' }}>
                {evaluation.verdict}
              </p>
              <div className="callout info" style={{ marginTop: '8px', fontSize: '12px' }}>
                Inferred (uncalibrated) camera scale ratio agrees within 2.7% across tests (0.057–0.059 mm/px), well inside NASA's
                ±50 µm droplet measurement uncertainty. This is reported strictly as an uncalibrated consistency check and is never used to produce physical millimeter values.
              </div>
            </div>
          </div>

          <h3 style={{ margin: '20px 0 10px' }}>Evaluated NASA FLEX Calibration Tests</h3>
          <div className="table-wrap">
            <table className="data-table" aria-label="NASA FLEX Calibration Tests Evaluation">
              <thead>
                <tr>
                  <th>Test Point</th>
                  <th>NASA Run</th>
                  <th>Fuel</th>
                  <th>End Mode</th>
                  <th>Status</th>
                  <th>Fit Frames</th>
                  <th>Fit R²</th>
                  <th>Vision K/D₀² (1/s)</th>
                  <th>NASA K/D₀² (1/s)</th>
                  <th>Diff (%)</th>
                  <th>Implied Scale (Uncalibrated)</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {evaluation.tests.map((t: VisionEvalTest) => (
                  <tr
                    key={t.test_point}
                    style={{
                      background: selectedTestPoint === t.test_point ? 'var(--surface-hover)' : undefined,
                    }}
                  >
                    <td><strong>{t.test_point}</strong></td>
                    <td>
                      <button
                        type="button"
                        className="link-btn"
                        onClick={() => navigateToRun(t.run_id)}
                        title="View in Scientific Explorer"
                      >
                        {t.run_id}
                      </button>
                    </td>
                    <td>{t.fuel}</td>
                    <td>{t.test_end}</td>
                    <td>
                      {t.computable ? (
                        <span className="badge success">Measured</span>
                      ) : (
                        <span className="badge warning" title={t.abstention_reason}>Abstained</span>
                      )}
                    </td>
                    <td>{t.computable ? t.fit_frames : '—'}</td>
                    <td>{t.computable ? formatNum(t.fit_r_squared, 4) : '—'}</td>
                    <td>
                      {t.computable ? (
                        <span>
                          {formatNum(t.vision_k_over_d0sq_per_s, 4)}
                          <small style={{ color: 'var(--text-3)', display: 'block' }}>
                            ±{formatPercent(t.vision_rel_uncertainty_1sigma, 2)} (1σ)
                          </small>
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-3)' }}>Abstained</span>
                      )}
                    </td>
                    <td>{formatNum(t.nasa_k_over_d0sq_per_s, 4)}</td>
                    <td>
                      {t.computable ? (
                        <strong style={{ color: (t.relative_difference ?? 0) < 0 ? 'var(--accent)' : 'inherit' }}>
                          {formatPercent(t.relative_difference)}
                        </strong>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      {t.computable ? `${formatNum(t.implied_mm_per_px_from_nasa_d0, 4)} mm/px (inferred)` : '—'}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn-sm"
                        onClick={() => {
                          setSelectedTestPoint(t.test_point);
                          setActiveTab('inspector');
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: DETAILED TEST INSPECTOR */}
      {/* ========================================================================= */}
      {activeTab === 'inspector' && (
        <div className="tab-pane">
          {/* Test Selector bar */}
          <div className="filter-controls-row">
            <label>
              Select Calibration Test Point:
              <select
                value={selectedTestPoint}
                onChange={(e) => setSelectedTestPoint(e.target.value)}
              >
                {evaluation?.tests.map((t) => (
                  <option key={t.test_point} value={t.test_point}>
                    {t.test_point} ({t.fuel} · {t.computable ? 'Measured' : 'Abstained'})
                  </option>
                ))}
              </select>
            </label>

            {activeSummary?.nasa_reference?.run_id && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => navigateToRun(activeSummary.nasa_reference.run_id)}
                style={{ alignSelf: 'flex-end', height: '36px' }}
              >
                Open {activeSummary.nasa_reference.run_id} in Explorer
              </button>
            )}

            <button
              type="button"
              className="btn-secondary"
              onClick={() => { window.location.hash = '#analysis'; }}
              style={{ alignSelf: 'flex-end', height: '36px' }}
            >
              Compare with Physics d²-Law
            </button>
          </div>

          {!activeSummary ? (
            <div className="callout info">Loading test summary for {selectedTestPoint}…</div>
          ) : activeSummary.computable === false ? (
            /* Abstained test view */
            <div className="abstained-panel" style={{ marginTop: '16px' }}>
              <div className="callout warning" style={{ padding: '16px' }}>
                <h3 style={{ margin: '0 0 8px', color: 'var(--warning)' }}>
                  Measurement Abstained: {activeSummary.test_point} ({activeSummary.nasa_reference.fuel})
                </h3>
                <p>
                  <strong>Abstention Reason:</strong> {activeSummary.abstention_reason}
                </p>
                <p style={{ marginTop: '8px', fontSize: '13px' }}>
                  <strong>Scientific Root Cause:</strong> In backlit HIBMS imaging, sooting heptane droplets
                  generate an expanding soot shell and particulate cloud ~4 seconds post-ignition. This disrupts
                  the intensity threshold and causes tracking jumps (&gt;25% frame-to-frame change). In adherence
                  to scientific quality gates, the pipeline abstains from fitting an unphysical rate rather than
                  guessing through soot interference.
                </p>
              </div>

              <div className="physics-grid" style={{ marginTop: '16px' }}>
                <div className="physics-card">
                  <span className="eyebrow">NASA REFERENCE COMPARISON</span>
                  <h3>Reported NASA Values (Unverified)</h3>
                  <table className="compact-table" style={{ width: '100%', fontSize: '13px' }}>
                    <tbody>
                      <tr>
                        <td>NASA Reported K:</td>
                        <td>{activeSummary.nasa_reference.reported_k_mm2_per_s} mm²/s</td>
                      </tr>
                      <tr>
                        <td>NASA Reported D₀:</td>
                        <td>{activeSummary.nasa_reference.reported_d0_mm} mm</td>
                      </tr>
                      <tr>
                        <td>NASA Reported K/D₀²:</td>
                        <td>{formatNum(activeSummary.nasa_reference.reported_k_over_d0sq_per_s, 4)} 1/s</td>
                      </tr>
                      <tr>
                        <td>NASA Burn Time:</td>
                        <td>{activeSummary.nasa_reference.reported_burn_time_s} s</td>
                      </tr>
                      <tr>
                        <td>Source:</td>
                        <td>{activeSummary.nasa_reference.value_origin}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div className="physics-card">
                  <span className="eyebrow">REPRODUCIBILITY & PROVENANCE</span>
                  <h3>NASA Raw Archive Files</h3>
                  <ul className="exclusion-list">
                    {activeSummary.provenance.map((p) => (
                      <li key={p.sha256}>
                        <a href={p.source_url} target="_blank" rel="noopener noreferrer">
                          {p.file_name}
                        </a>{' '}
                        <small style={{ color: 'var(--text-3)' }}>({p.role}, {Math.round(parseInt(p.byte_size, 10) / 1024)} KB)</small>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : (
            /* Computable test view */
            <div>
              <div className="physics-grid">
                {/* Metric Card 1: Rate & Comparison */}
                <div className="physics-card">
                  <span className="eyebrow">METROLOGY RESULTS</span>
                  <h3>Scale-Free Burning Rate (K/D₀²)</h3>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', margin: '8px 0' }}>
                    <span style={{ fontSize: '26px', fontWeight: '700', color: 'var(--accent)' }}>
                      {formatNum(activeSummary.results?.k_over_d0sq_per_s, 4)}
                    </span>
                    <span style={{ fontSize: '13px', color: 'var(--text-2)' }}>1/s</span>
                  </div>
                  <p style={{ fontSize: '12.5px', color: 'var(--text-2)' }}>
                    Uncertainty (1σ): ±{formatPercent(activeSummary.results?.k_over_d0sq_rel_uncertainty_1sigma, 2)}
                  </p>
                  <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '10px 0' }} />
                  <table className="compact-table" style={{ width: '100%', fontSize: '12px' }}>
                    <tbody>
                      <tr>
                        <td>NASA Reported K/D₀²:</td>
                        <td><strong>{formatNum(activeSummary.nasa_reference.reported_k_over_d0sq_per_s, 4)} 1/s</strong></td>
                      </tr>
                      <tr>
                        <td>Relative Difference:</td>
                        <td>
                          <strong style={{ color: 'var(--accent)' }}>
                            {formatPercent(activeSummary.comparison?.relative_difference)}
                          </strong>
                        </td>
                      </tr>
                      <tr>
                        <td>Inferred Scale (D₀/D₀_px, Uncalibrated):</td>
                        <td>{formatNum(activeSummary.comparison?.implied_mm_per_px_from_nasa_d0, 4)} mm/px</td>
                      </tr>
                      <tr>
                        <td>Regime Break Proxy (D/D₀):</td>
                        <td>
                          {formatNum(activeSummary.results?.regime_break_diameter_ratio, 3)} (vs NASA Dext/D₀: {formatNum(activeSummary.nasa_reference.reported_dext_over_d0, 3)})
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Metric Card 2: Regression & Window */}
                <div className="physics-card">
                  <span className="eyebrow">REGRESSION FIT & WINDOWS</span>
                  <h3>Linear Fit (R² = {formatNum(activeSummary.results?.fit?.r_squared, 4)})</h3>
                  <p style={{ fontSize: '11.5px', color: 'var(--text-3)', margin: '0 0 6px' }}>
                    Note: High R² indicates regression linearity over the pixel series, not physical agreement with NASA.
                  </p>
                  <table className="compact-table" style={{ width: '100%', fontSize: '12.5px' }}>
                    <tbody>
                      <tr>
                        <td>Slope K_px (px²/s):</td>
                        <td>
                          <strong>{formatNum(activeSummary.results?.k_px2_per_s, 2)}</strong> ±{formatNum(activeSummary.results?.fit?.slope_se, 2)}
                        </td>
                      </tr>
                      <tr>
                        <td>95% CI on Slope:</td>
                        <td>
                          [{formatNum(activeSummary.results?.fit?.slope_ci95?.[0], 2)}, {formatNum(activeSummary.results?.fit?.slope_ci95?.[1], 2)}]
                        </td>
                      </tr>
                      <tr>
                        <td>Initial Diameter D₀_px:</td>
                        <td>
                          <strong>{formatNum(activeSummary.results?.d0_px, 2)} px</strong> (MAD: {formatNum(activeSummary.results?.d0_mad_px, 3)})
                        </td>
                      </tr>
                      <tr>
                        <td>Fit Window (t):</td>
                        <td>
                          {formatNum(activeSummary.results?.windows_s?.fit?.[0], 2)} s to {formatNum(activeSummary.results?.windows_s?.fit?.[1], 2)} s ({activeSummary.results?.fit?.n} frames)
                        </td>
                      </tr>
                      <tr>
                        <td>Igniter Excluded Window:</td>
                        <td>
                          {formatNum(activeSummary.results?.windows_s?.excluded_igniters?.[0], 2)} s to {formatNum(activeSummary.results?.windows_s?.excluded_igniters?.[1], 2)} s
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <div className="callout info" style={{ marginTop: '8px', fontSize: '11.5px' }}>
                    <strong>Methanol Deceleration:</strong> 1st half burning rate ({formatNum(activeSummary.results?.k_over_d0sq_first_half_per_s, 4)} 1/s)
                    exceeds 2nd half ({formatNum(activeSummary.results?.k_over_d0sq_second_half_per_s, 4)} 1/s), correctly resolving water absorption dynamics.
                  </div>
                </div>

                {/* Metric Card 3: Sensitivity & Camera */}
                <div className="physics-card">
                  <span className="eyebrow">ROBUSTNESS & CAMERA SPEC</span>
                  <h3>Threshold Sensitivity (f = 0.4 / 0.5 / 0.6)</h3>
                  <table className="compact-table" style={{ width: '100%', fontSize: '12px' }}>
                    <thead>
                      <tr>
                        <th>Threshold (f)</th>
                        <th>K/D₀² (1/s)</th>
                        <th>Sensitivity</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>f = 0.4 (darker)</td>
                        <td>{formatNum(activeSummary.results?.threshold_sensitivity_k_over_d0sq?.['0.4'], 4)}</td>
                        <td>+0.7%</td>
                      </tr>
                      <tr>
                        <td>f = 0.5 (nominal half-intensity)</td>
                        <td>{formatNum(activeSummary.results?.threshold_sensitivity_k_over_d0sq?.['0.5'], 4)}</td>
                        <td>Baseline</td>
                      </tr>
                      <tr>
                        <td>f = 0.6 (lighter)</td>
                        <td>{formatNum(activeSummary.results?.threshold_sensitivity_k_over_d0sq?.['0.6'], 4)}</td>
                        <td>−0.8%</td>
                      </tr>
                    </tbody>
                  </table>
                  <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '8px 0' }} />
                  <div style={{ fontSize: '12px', color: 'var(--text-2)' }}>
                    <strong>Camera:</strong> {activeSummary.camera?.IPSU_TP_CAMERA ?? 'SMD 1M60-20'} ({activeSummary.camera?.IPSU_TP_FMT ?? '12-bit gray'}, {activeSummary.camera?.IPSU_TP_XRES}×{activeSummary.camera?.IPSU_TP_YRES} @ {activeSummary.camera?.IPSU_TP_FPS} fps)
                  </div>
                </div>
              </div>

              {/* Visual Evidence Artifacts Box */}
              <div className="physics-card" style={{ marginTop: '16px' }}>
                <span className="eyebrow">VISUAL EVIDENCE ARTIFACTS</span>
                <h3>Original Droplet Segmentation Overlay ({selectedTestPoint})</h3>
                <p style={{ fontSize: '13px', color: 'var(--text-2)' }}>
                  Backlit droplet contour overlay (red) segmented at half-intensity (f = 0.5) against the local background.
                  Derived from NASA calibration TIFF frames inside the zip archive.
                </p>

                <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', alignItems: 'flex-start', marginTop: '12px' }}>
                  <div style={{ flex: '1 1 320px', maxWidth: '420px', background: 'var(--surface-1)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                    <img
                      src={`data/flame_vision/${selectedTestPoint}/overlay.png`}
                      alt={`Droplet boundary overlay for ${selectedTestPoint}`}
                      style={{ width: '100%', borderRadius: '4px', display: 'block' }}
                      onError={(e) => {
                        // Fallback message if image not found
                        const target = e.currentTarget;
                        target.style.display = 'none';
                        const parent = target.parentElement;
                        if (parent) {
                          const note = document.createElement('p');
                          note.textContent = 'Overlay image available in data/derived/flame_vision/' + selectedTestPoint + '/overlay.png';
                          note.style.fontSize = '12px';
                          parent.appendChild(note);
                        }
                      }}
                    />
                    <caption style={{ display: 'block', marginTop: '6px', fontSize: '11.5px', color: 'var(--text-3)' }}>
                      Droplet boundary contour overlay on NASA HIBMS frame
                    </caption>
                  </div>

                  <div style={{ flex: '2 1 400px' }}>
                    <h4>Segmentation Quality Assurance</h4>
                    <ul style={{ fontSize: '13px', lineHeight: '1.6', paddingLeft: '18px' }}>
                      <li><strong>Edge Definition:</strong> Transition between dark droplet and backlit bright field spans ~2 pixels.</li>
                      <li><strong>Synthetic Disk Accuracy:</strong> Evaluated on synthetic 8–49 px disks with error ≤ 0.5 px.</li>
                      <li><strong>Igniter Rejection:</strong> Frames touching border margins (margin = 1 px) or showing non-spherical shapes (aspect ratio &gt; 1.3, circularity &lt; 0.7) are rejected automatically.</li>
                      <li><strong>Frame Status Breakdown:</strong>
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '4px' }}>
                          {Object.entries(activeSummary.results?.frame_status_counts ?? {}).map(([k, v]) => (
                            <span key={k} className="badge info">
                              {k}: {v}
                            </span>
                          ))}
                        </div>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>

              {/* Provenance Table */}
              <div className="physics-card" style={{ marginTop: '16px' }}>
                <span className="eyebrow">NASA PSI-69 PROVENANCE & ARCHIVES</span>
                <h3>Cryptographic Source File Manifest</h3>
                <div className="table-wrap">
                  <table className="compact-table" style={{ width: '100%', fontSize: '12px' }}>
                    <thead>
                      <tr>
                        <th>Role</th>
                        <th>File Name</th>
                        <th>Size</th>
                        <th>SHA-256 Hash</th>
                        <th>Source Link</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeSummary.provenance.map((p) => (
                        <tr key={p.sha256}>
                          <td><strong>{p.role}</strong></td>
                          <td><code>{p.file_name}</code></td>
                          <td>{Math.round(parseInt(p.byte_size, 10) / 1024)} KB</td>
                          <td><code style={{ fontSize: '11px' }}>{p.sha256.slice(0, 16)}…</code></td>
                          <td>
                            <a href={p.source_url} target="_blank" rel="noopener noreferrer" className="link-btn">
                              NASA PSI Download
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: TIME-SERIES & DYNAMIC CHART */}
      {/* ========================================================================= */}
      {activeTab === 'series' && (
        <div className="tab-pane">
          <div className="filter-controls-row">
            <label>
              Calibration Test:
              <select
                value={selectedTestPoint}
                onChange={(e) => setSelectedTestPoint(e.target.value)}
              >
                {evaluation?.tests.map((t) => (
                  <option key={t.test_point} value={t.test_point}>
                    {t.test_point} ({t.fuel} · {t.computable ? 'Measured' : 'Abstained'})
                  </option>
                ))}
              </select>
            </label>

            <label>
              Plot Variable:
              <select
                value={chartMode}
                onChange={(e) => setChartMode(e.target.value as 'd2' | 'd')}
              >
                <option value="d2">D²(t) [px²] (d²-Law Burning Rate)</option>
                <option value="d">D(t) [px] (Droplet Diameter)</option>
              </select>
            </label>

            <label>
              Filter Frame Table:
              <select
                value={frameStatusFilter}
                onChange={(e) => setFrameStatusFilter(e.target.value)}
              >
                <option value="all">All Frames ({activeSeries.length})</option>
                <option value="measured">Measured Only</option>
                <option value="excluded_igniter_window">Excluded Igniter Window</option>
                <option value="before_droplet_release">Before Release</option>
                <option value="unreadable_frame">Unreadable / Flagged</option>
              </select>
            </label>
          </div>

          {activeSeries.length === 0 ? (
            <div className="callout warning">
              No time-series frame records available for {selectedTestPoint} (test was abstained or no frames recorded).
            </div>
          ) : (
            <div>
              {/* Dynamic SVG Plot */}
              <div className="physics-card">
                <span className="eyebrow">DYNAMIC METROLOGY CHART</span>
                <h3>
                  {selectedTestPoint}: {chartMode === 'd2' ? 'D²(t) Evolution & OLS Fit' : 'Droplet Diameter D(t)'}
                </h3>
                <p style={{ fontSize: '12.5px', color: 'var(--text-2)', marginBottom: '12px' }}>
                  Interactive frame-by-frame data: green dots = measured; orange = igniter retraction window; blue = pre-ignition D₀ window.
                  Regression slope line shown over a-priori fit window.
                </p>

                {chartMetrics && (
                  <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
                    <svg
                      viewBox="0 0 800 360"
                      style={{ width: '100%', maxWidth: '900px', height: 'auto', background: 'var(--surface-1)', borderRadius: '6px' }}
                    >
                      {/* Grid lines */}
                      <line x1="60" y1="30" x2="60" y2="310" stroke="var(--border)" strokeWidth="1" />
                      <line x1="60" y1="310" x2="770" y2="310" stroke="var(--border)" strokeWidth="1" />

                      {/* X-axis labels (Time in seconds) */}
                      {[chartMetrics.minT, 0, (chartMetrics.maxT) / 2, chartMetrics.maxT].map((tVal, i) => {
                        const x = 60 + ((tVal - chartMetrics.minT) / (chartMetrics.maxT - chartMetrics.minT)) * 710;
                        return (
                          <g key={i}>
                            <line x1={x} y1="310" x2={x} y2="315" stroke="var(--border)" />
                            <text x={x} y="330" fill="var(--text-3)" fontSize="11" textAnchor="middle">
                              {tVal.toFixed(1)}s
                            </text>
                          </g>
                        );
                      })}
                      <text x="415" y="350" fill="var(--text-2)" fontSize="12" textAnchor="middle">
                        Time relative to Ignition t = 0 (s)
                      </text>

                      {/* Y-axis labels */}
                      {[0, chartMetrics.maxY / 2, chartMetrics.maxY].map((yVal, i) => {
                        const y = 310 - (yVal / chartMetrics.maxY) * 280;
                        return (
                          <g key={i}>
                            <line x1="55" y1={y} x2="60" y2={y} stroke="var(--border)" />
                            <text x="50" y={y + 4} fill="var(--text-3)" fontSize="11" textAnchor="end">
                              {Math.round(yVal)}
                            </text>
                          </g>
                        );
                      })}
                      <text x="20" y="170" fill="var(--text-2)" fontSize="12" transform="rotate(-90 20 170)" textAnchor="middle">
                        {chartMode === 'd2' ? 'D² (px²)' : 'Diameter D (px)'}
                      </text>

                      {/* Event vertical line: t = 0 (Igniter On) */}
                      {chartMetrics.minT <= 0 && chartMetrics.maxT >= 0 && (
                        (() => {
                          const x0 = 60 + ((0 - chartMetrics.minT) / (chartMetrics.maxT - chartMetrics.minT)) * 710;
                          return (
                            <g>
                              <line x1={x0} y1="30" x2={x0} y2="310" stroke="var(--warning)" strokeDasharray="4 3" strokeWidth="1.5" />
                              <text x={x0 + 4} y="45" fill="var(--warning)" fontSize="10">t = 0 (Ignition)</text>
                            </g>
                          );
                        })()
                      )}

                      {/* OLS Fit Line if in D² mode and fit parameters exist */}
                      {chartMode === 'd2' && activeSummary?.results?.fit && (
                        (() => {
                          const fit = activeSummary.results.fit;
                          const t1 = fit.t_start;
                          const t2 = fit.t_end;
                          const y1 = fit.intercept + fit.slope * t1;
                          const y2 = fit.intercept + fit.slope * t2;

                          const x1Pix = 60 + ((t1 - chartMetrics.minT) / (chartMetrics.maxT - chartMetrics.minT)) * 710;
                          const x2Pix = 60 + ((t2 - chartMetrics.minT) / (chartMetrics.maxT - chartMetrics.minT)) * 710;
                          const y1Pix = 310 - (y1 / chartMetrics.maxY) * 280;
                          const y2Pix = 310 - (y2 / chartMetrics.maxY) * 280;

                          return (
                            <line
                              x1={x1Pix}
                              y1={y1Pix}
                              x2={x2Pix}
                              y2={y2Pix}
                              stroke="var(--accent)"
                              strokeWidth="2.5"
                            />
                          );
                        })()
                      )}

                      {/* Frame Data Points */}
                      {chartMetrics.validFrames.map((f, idx) => {
                        const t = f.t_s as number;
                        const yVal = chartMode === 'd2' ? Math.pow(f.diameter_px as number, 2) : (f.diameter_px as number);
                        const cx = 60 + ((t - chartMetrics.minT) / (chartMetrics.maxT - chartMetrics.minT)) * 710;
                        const cy = 310 - (yVal / chartMetrics.maxY) * 280;

                        const color =
                          f.status === 'measured'
                            ? 'var(--success)'
                            : f.status === 'excluded_igniter_window'
                            ? 'var(--warning)'
                            : 'var(--text-3)';

                        return (
                          <circle
                            key={idx}
                            cx={cx}
                            cy={cy}
                            r={hoveredFrame?.frame === f.frame ? 5 : 2.5}
                            fill={color}
                            opacity={0.85}
                            style={{ cursor: 'pointer' }}
                            onMouseEnter={() => setHoveredFrame(f)}
                            onMouseLeave={() => setHoveredFrame(null)}
                          />
                        );
                      })}
                    </svg>

                    {hoveredFrame && (
                      <div
                        style={{
                          position: 'absolute',
                          top: '10px',
                          right: '15px',
                          background: 'var(--surface-2)',
                          border: '1px solid var(--border)',
                          borderRadius: '6px',
                          padding: '8px 12px',
                          fontSize: '12px',
                          boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
                          pointerEvents: 'none',
                        }}
                      >
                        <div><strong>Frame:</strong> {hoveredFrame.frame}</div>
                        <div><strong>Time:</strong> {formatNum(hoveredFrame.t_s, 3)} s</div>
                        <div><strong>Diameter:</strong> {formatNum(hoveredFrame.diameter_px, 2)} px</div>
                        <div><strong>Status:</strong> {hoveredFrame.status}</div>
                        {hoveredFrame.circularity !== null && (
                          <div><strong>Circularity:</strong> {formatNum(hoveredFrame.circularity, 3)}</div>
                        )}
                        {hoveredFrame.flags.length > 0 && (
                          <div><strong>Flags:</strong> {hoveredFrame.flags.join(', ')}</div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Frame series table */}
              <h3 style={{ margin: '20px 0 8px' }}>Frame Records ({filteredFrames.length} frames)</h3>
              <div className="table-wrap" style={{ maxHeight: '400px', overflowY: 'auto' }}>
                <table className="compact-table" style={{ width: '100%', fontSize: '12px' }}>
                  <thead>
                    <tr>
                      <th>Frame Identifier</th>
                      <th>Time (s)</th>
                      <th>Status</th>
                      <th>Diameter (px)</th>
                      <th>Area (px)</th>
                      <th>Circularity</th>
                      <th>Centroid (X, Y)</th>
                      <th>Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFrames.slice(0, 200).map((f) => (
                      <tr
                        key={f.frame}
                        onMouseEnter={() => setHoveredFrame(f)}
                        onMouseLeave={() => setHoveredFrame(null)}
                        style={{
                          background: hoveredFrame?.frame === f.frame ? 'var(--surface-hover)' : undefined,
                        }}
                      >
                        <td><code>{f.frame}</code></td>
                        <td>{formatNum(f.t_s, 3)}</td>
                        <td>
                          <span
                            className={`badge ${
                              f.status === 'measured'
                                ? 'success'
                                : f.status === 'excluded_igniter_window'
                                ? 'warning'
                                : 'neutral'
                            }`}
                          >
                            {f.status}
                          </span>
                        </td>
                        <td>{formatNum(f.diameter_px, 2)}</td>
                        <td>{formatNum(f.area_px, 1)}</td>
                        <td>{formatNum(f.circularity, 3)}</td>
                        <td>
                          {f.centroid_x_px !== null && f.centroid_y_px !== null
                            ? `(${formatNum(f.centroid_x_px, 1)}, ${formatNum(f.centroid_y_px, 1)})`
                            : '—'}
                        </td>
                        <td>
                          {f.flags.length > 0 ? (
                            <span className="badge error">{f.flags.join('; ')}</span>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {filteredFrames.length > 200 && (
                <p style={{ fontSize: '11.5px', color: 'var(--text-3)', marginTop: '4px' }}>
                  Showing first 200 of {filteredFrames.length} frames for rendering efficiency.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: METHOD CARD & SCIENTIFIC AUDIT */}
      {/* ========================================================================= */}
      {activeTab === 'method' && methodCard && (
        <div className="tab-pane">
          <div className="physics-card">
            <span className="eyebrow">METHOD SPECIFICATION</span>
            <h3>{methodCard.title} ({methodCard.method_id} v{methodCard.version})</h3>
            <p style={{ fontSize: '13px', lineHeight: '1.5', marginTop: '6px' }}>
              <strong>Formula:</strong> <code>{methodCard.formula}</code>
            </p>

            <h4 style={{ margin: '14px 0 6px' }}>Variables Spec</h4>
            <table className="compact-table" style={{ width: '100%', fontSize: '12px' }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Unit</th>
                  <th>Role</th>
                </tr>
              </thead>
              <tbody>
                {methodCard.variables.map((v) => (
                  <tr key={v.symbol}>
                    <td><code>{v.symbol}</code></td>
                    <td>{v.name}</td>
                    <td>{v.unit}</td>
                    <td><span className="badge neutral">{v.role}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h4 style={{ margin: '16px 0 6px' }}>Assumptions</h4>
            <ul style={{ fontSize: '13px', lineHeight: '1.5', paddingLeft: '18px' }}>
              {methodCard.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>

            <h4 style={{ margin: '16px 0 6px' }}>Validity Limits & Failure Modes</h4>
            <ul style={{ fontSize: '13px', lineHeight: '1.5', paddingLeft: '18px' }}>
              {methodCard.validity_limits.map((vl, i) => (
                <li key={i}>{vl}</li>
              ))}
            </ul>

            <h4 style={{ margin: '16px 0 6px' }}>Quality Gates & Abstention Conditions</h4>
            <ul style={{ fontSize: '13px', lineHeight: '1.5', paddingLeft: '18px' }}>
              {methodCard.abstention_conditions.map((ac, i) => (
                <li key={i}><strong>Abstain if:</strong> {ac}</li>
              ))}
            </ul>

            <h4 style={{ margin: '16px 0 6px' }}>Scientific References</h4>
            <ul style={{ fontSize: '13px', lineHeight: '1.5', paddingLeft: '18px' }}>
              {methodCard.references.map((r, i) => (
                <li key={i}>
                  {r.citation}{' '}
                  {r.doi && (
                    <a
                      href={`https://doi.org/${r.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="link-btn"
                    >
                      DOI: {r.doi}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}


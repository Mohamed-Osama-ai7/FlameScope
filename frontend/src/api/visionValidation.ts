import type {
  VisionComparison,
  VisionEvalTest,
  VisionEvaluation,
  VisionFitResult,
  VisionFrame,
  VisionNasaReference,
  VisionTestSummary,
  VisionThresholdSensitivity,
} from './contracts';

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === 'string';
const isNum = (v: unknown): v is number => typeof v === 'number';
const isBool = (v: unknown): v is boolean => typeof v === 'boolean';
const strList = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr);

function fail(what: string): never {
  throw new Error(`${what} response has an invalid shape.`);
}

function numPair(v: unknown): v is [number, number] {
  return Array.isArray(v) && v.length === 2 && v.every(isNum);
}

export function parseThresholdSensitivity(p: unknown): VisionThresholdSensitivity {
  if (!isObj(p) || !isNum(p['0.4']) || !isNum(p['0.5']) || !isNum(p['0.6'])) {
    fail('ThresholdSensitivity');
  }
  return { '0.4': p['0.4'], '0.5': p['0.5'], '0.6': p['0.6'] };
}

export function parseVisionEvalTest(p: unknown): VisionEvalTest {
  if (!isObj(p)) fail('VisionEvalTest');
  if (!isStr(p.test_point) || !isStr(p.run_id) || !isStr(p.fuel) || !isStr(p.test_end) || !isBool(p.computable)) {
    fail('VisionEvalTest');
  }
  const base: VisionEvalTest = {
    test_point: p.test_point,
    run_id: p.run_id,
    fuel: p.fuel,
    test_end: p.test_end,
    computable: p.computable,
  };
  if (p.computable) {
    if (
      !isNum(p.fit_frames) ||
      !isNum(p.fit_r_squared) ||
      !isNum(p.fit_window_coverage) ||
      !isNum(p.vision_k_over_d0sq_per_s) ||
      !isNum(p.vision_rel_uncertainty_1sigma) ||
      !isNum(p.nasa_k_over_d0sq_per_s) ||
      !isNum(p.relative_difference) ||
      !isNum(p.implied_mm_per_px_from_nasa_d0)
    ) {
      fail('VisionEvalTest (computable fields)');
    }
    base.fit_frames = p.fit_frames;
    base.fit_r_squared = p.fit_r_squared;
    base.fit_window_coverage = p.fit_window_coverage;
    base.vision_k_over_d0sq_per_s = p.vision_k_over_d0sq_per_s;
    base.vision_rel_uncertainty_1sigma = p.vision_rel_uncertainty_1sigma;
    base.nasa_k_over_d0sq_per_s = p.nasa_k_over_d0sq_per_s;
    base.relative_difference = p.relative_difference;
    base.implied_mm_per_px_from_nasa_d0 = p.implied_mm_per_px_from_nasa_d0;
    if (isObj(p.threshold_sensitivity)) {
      base.threshold_sensitivity = parseThresholdSensitivity(p.threshold_sensitivity);
    }
  } else {
    if (isStr(p.abstention_reason)) base.abstention_reason = p.abstention_reason;
  }
  return base;
}

export function parseVisionEvaluation(p: unknown): VisionEvaluation {
  if (!isObj(p)) fail('VisionEvaluation');
  if (
    !isStr(p.method_id) ||
    !isStr(p.method_version) ||
    !Array.isArray(p.tests) ||
    !isNum(p.n_tests) ||
    !isNum(p.n_computable) ||
    !isNum(p.n_abstained) ||
    !isNum(p.relative_difference_mean) ||
    !numPair(p.relative_difference_range) ||
    !numPair(p.implied_scale_range_mm_per_px) ||
    !isStr(p.verdict)
  ) {
    fail('VisionEvaluation');
  }
  return {
    method_id: p.method_id,
    method_version: p.method_version,
    tests: p.tests.map(parseVisionEvalTest),
    n_tests: p.n_tests,
    n_computable: p.n_computable,
    n_abstained: p.n_abstained,
    relative_difference_mean: p.relative_difference_mean,
    relative_difference_range: [p.relative_difference_range[0], p.relative_difference_range[1]],
    implied_scale_range_mm_per_px: [p.implied_scale_range_mm_per_px[0], p.implied_scale_range_mm_per_px[1]],
    verdict: p.verdict,
  };
}

function parseFitResult(p: unknown): VisionFitResult {
  if (!isObj(p)) fail('VisionFitResult');
  if (
    !isNum(p.slope) || !isNum(p.intercept) || !isNum(p.slope_se) ||
    !numPair(p.slope_ci95) || !isNum(p.r_squared) || !isNum(p.n) ||
    !isNum(p.t_start) || !isNum(p.t_end) || !isNum(p.slope_px2_per_s)
  ) {
    fail('VisionFitResult');
  }
  return {
    slope: p.slope,
    intercept: p.intercept,
    slope_se: p.slope_se,
    slope_ci95: [p.slope_ci95[0], p.slope_ci95[1]],
    r_squared: p.r_squared,
    n: p.n,
    t_start: p.t_start,
    t_end: p.t_end,
    slope_px2_per_s: p.slope_px2_per_s,
  };
}

function parseNasaReference(p: unknown): VisionNasaReference {
  if (!isObj(p)) fail('VisionNasaReference');
  if (
    !isStr(p.run_id) || !isStr(p.flex_identifier) || !isStr(p.fuel) || !isStr(p.test_end) ||
    !isNum(p.reported_k_mm2_per_s) || !isNum(p.reported_d0_mm) || !isNum(p.reported_burn_time_s) ||
    !isNum(p.reported_k_over_d0sq_per_s) || !isStr(p.value_origin)
  ) {
    fail('VisionNasaReference');
  }
  return {
    run_id: p.run_id,
    flex_identifier: p.flex_identifier,
    fuel: p.fuel,
    test_end: p.test_end,
    reported_k_mm2_per_s: p.reported_k_mm2_per_s,
    reported_d0_mm: p.reported_d0_mm,
    reported_extinction_diameter_mm: isNum(p.reported_extinction_diameter_mm) ? p.reported_extinction_diameter_mm : null,
    reported_burn_time_s: p.reported_burn_time_s,
    reported_k_over_d0sq_per_s: p.reported_k_over_d0sq_per_s,
    reported_dext_over_d0: isNum(p.reported_dext_over_d0) ? p.reported_dext_over_d0 : null,
    value_origin: p.value_origin,
  };
}

function parseComparison(p: unknown): VisionComparison {
  if (!isObj(p)) fail('VisionComparison');
  if (
    !isNum(p.nasa_k_over_d0sq_per_s) || !isNum(p.vision_k_over_d0sq_per_s) ||
    !isNum(p.relative_difference) || !isNum(p.implied_mm_per_px_from_nasa_d0) ||
    !isStr(p.implied_scale_note) ||
    !isNum(p.vision_regime_break_diameter_ratio_proxy) || !isStr(p.note)
  ) {
    fail('VisionComparison');
  }
  return {
    nasa_k_over_d0sq_per_s: p.nasa_k_over_d0sq_per_s,
    vision_k_over_d0sq_per_s: p.vision_k_over_d0sq_per_s,
    relative_difference: p.relative_difference,
    nasa_dext_over_d0: isNum(p.nasa_dext_over_d0) ? p.nasa_dext_over_d0 : null,
    implied_mm_per_px_from_nasa_d0: p.implied_mm_per_px_from_nasa_d0,
    implied_scale_note: p.implied_scale_note,
    vision_regime_break_diameter_ratio_proxy: p.vision_regime_break_diameter_ratio_proxy,
    note: p.note,
  };
}

export function parseVisionTestSummary(p: unknown): VisionTestSummary {
  if (!isObj(p)) fail('VisionTestSummary');
  if (!isStr(p.test_point) || !isObj(p.method) || !isStr(p.generated_at_utc)) {
    fail('VisionTestSummary');
  }
  const method = p.method as Obj;
  if (!isStr(method.method_id) || !isStr(method.version) || !isStr(method.status)) {
    fail('VisionTestSummary.method');
  }
  const result: VisionTestSummary = {
    test_point: p.test_point,
    method: { method_id: method.method_id, version: method.version, status: method.status },
    physical_units: null,
    physical_units_reason: isStr(p.physical_units_reason) ? p.physical_units_reason : '',
    nasa_reference: parseNasaReference(p.nasa_reference),
    provenance: Array.isArray(p.provenance) ? p.provenance.map((item: unknown) => {
      const it = item as Obj;
      return {
        source_id: String(it.source_id ?? ''),
        test_point: String(it.test_point ?? ''),
        role: String(it.role ?? ''),
        file_name: String(it.file_name ?? ''),
        relative_path: String(it.relative_path ?? ''),
        byte_size: String(it.byte_size ?? ''),
        sha256: String(it.sha256 ?? ''),
        source_url: String(it.source_url ?? ''),
        license: String(it.license ?? ''),
        retrieved_at_utc: String(it.retrieved_at_utc ?? ''),
      };
    }) : [],
    generated_at_utc: p.generated_at_utc,
  };
  if (isBool(p.computable)) result.computable = p.computable;
  if (isStr(p.abstention_reason)) result.abstention_reason = p.abstention_reason;
  if (isObj(p.camera)) {
    const cam: Record<string, string> = {};
    for (const [k, v] of Object.entries(p.camera)) if (isStr(v)) cam[k] = v;
    result.camera = cam;
  }
  if (isObj(p.results)) {
    const r = p.results as Obj;
    if (
      isNum(r.d0_px) && isNum(r.d0_mad_px) && isNum(r.d0_frames) &&
      isNum(r.fit_window_coverage) && isObj(r.fit) &&
      isNum(r.k_px2_per_s) && isNum(r.k_over_d0sq_per_s) &&
      isNum(r.k_over_d0sq_rel_uncertainty_1sigma) &&
      isNum(r.k_over_d0sq_first_half_per_s) && isNum(r.k_over_d0sq_second_half_per_s) &&
      isNum(r.regime_break_t_s) && isNum(r.regime_break_diameter_ratio) &&
      isObj(r.windows_s) && isObj(r.threshold_sensitivity_k_over_d0sq) &&
      isObj(r.frame_status_counts) && isNum(r.measured_frames_with_flags) && isObj(r.segmentation_params)
    ) {
      const ws = r.windows_s as Obj;
      const sp = r.segmentation_params as Obj;
      result.results = {
        d0_px: r.d0_px,
        d0_mad_px: r.d0_mad_px,
        d0_frames: r.d0_frames,
        fit_window_coverage: r.fit_window_coverage,
        fit: parseFitResult(r.fit),
        k_px2_per_s: r.k_px2_per_s,
        k_over_d0sq_per_s: r.k_over_d0sq_per_s,
        k_over_d0sq_rel_uncertainty_1sigma: r.k_over_d0sq_rel_uncertainty_1sigma,
        k_over_d0sq_first_half_per_s: r.k_over_d0sq_first_half_per_s,
        k_over_d0sq_second_half_per_s: r.k_over_d0sq_second_half_per_s,
        regime_break_t_s: r.regime_break_t_s,
        regime_break_diameter_ratio: r.regime_break_diameter_ratio,
        windows_s: {
          d0: numPair(ws.d0) ? [ws.d0[0], ws.d0[1]] : [0, 0],
          excluded_igniters: numPair(ws.excluded_igniters) ? [ws.excluded_igniters[0], ws.excluded_igniters[1]] : [0, 0],
          fit: numPair(ws.fit) ? [ws.fit[0], ws.fit[1]] : [0, 0],
        },
        threshold_sensitivity_k_over_d0sq: parseThresholdSensitivity(r.threshold_sensitivity_k_over_d0sq),
        frame_status_counts: (() => {
          const counts: Record<string, number> = {};
          for (const [k, v] of Object.entries(r.frame_status_counts as Obj)) if (isNum(v)) counts[k] = v;
          return counts;
        })(),
        measured_frames_with_flags: r.measured_frames_with_flags,
        segmentation_params: {
          threshold_fraction: isNum(sp.threshold_fraction) ? sp.threshold_fraction : 0.5,
          min_area_px: isNum(sp.min_area_px) ? sp.min_area_px : 6,
          max_aspect_ratio: isNum(sp.max_aspect_ratio) ? sp.max_aspect_ratio : 1.3,
          min_circularity: isNum(sp.min_circularity) ? sp.min_circularity : 0.7,
          border_margin_px: isNum(sp.border_margin_px) ? sp.border_margin_px : 1,
        },
      };
    }
  }
  if (isObj(p.comparison)) result.comparison = parseComparison(p.comparison);
  return result;
}

export function parseVisionFrame(p: unknown): VisionFrame {
  if (!isObj(p)) fail('VisionFrame');
  if (!isStr(p.frame) || !isStr(p.status) || !strList(p.flags)) {
    fail('VisionFrame');
  }
  return {
    frame: p.frame,
    t_s: isNum(p.t_s) ? p.t_s : null,
    status: p.status,
    diameter_px: isNum(p.diameter_px) ? p.diameter_px : null,
    area_px: isNum(p.area_px) ? p.area_px : null,
    circularity: isNum(p.circularity) ? p.circularity : null,
    centroid_x_px: isNum(p.centroid_x_px) ? p.centroid_x_px : null,
    centroid_y_px: isNum(p.centroid_y_px) ? p.centroid_y_px : null,
    candidates: isNum(p.candidates) ? p.candidates : null,
    flags: p.flags,
  };
}

export function parseVisionFrameList(p: unknown): VisionFrame[] {
  if (!Array.isArray(p)) fail('VisionFrame[]');
  return p.map(parseVisionFrame);
}


import type {
  D2ConsistencyResponse,
  D2FuelSummary,
  D2RunResult,
  OlsModelResult,
  OxygenEffectResponse,
  OxygenStratumResult,
  RegressionCoefficient,
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

export function parseD2FuelSummary(p: unknown): D2FuelSummary {
  if (!isObj(p)) fail('D2FuelSummary');
  if (
    !isNum(p.n) ||
    !isNum(p.median) ||
    !isNum(p.q1) ||
    !isNum(p.q3) ||
    !isNum(p.min) ||
    !isNum(p.max) ||
    !Array.isArray(p.tukey_fences) ||
    p.tukey_fences.length !== 2 ||
    !p.tukey_fences.every(isNum) ||
    !isNum(p.share_of_intervals_containing_1)
  ) {
    fail('D2FuelSummary');
  }
  let median_ci95: [number, number] | null = null;
  if (p.median_ci95 !== null) {
    if (!Array.isArray(p.median_ci95) || p.median_ci95.length !== 2 || !p.median_ci95.every(isNum)) {
      fail('D2FuelSummary median_ci95');
    }
    median_ci95 = [p.median_ci95[0], p.median_ci95[1]];
  }
  return {
    n: p.n,
    median: p.median,
    median_ci95,
    q1: p.q1,
    q3: p.q3,
    min: p.min,
    max: p.max,
    tukey_fences: [p.tukey_fences[0], p.tukey_fences[1]],
    share_of_intervals_containing_1: p.share_of_intervals_containing_1,
  };
}

export function parseD2RunResult(p: unknown): D2RunResult {
  if (!isObj(p)) fail('D2RunResult');
  if (
    !isStr(p.run_id) ||
    !isStr(p.experiment_id) ||
    !isStr(p.fuel) ||
    !isNum(p.d0_mm) ||
    !isNum(p.dext_mm) ||
    !isNum(p.k_mm2_s) ||
    !isNum(p.burn_time_s) ||
    !isNum(p.t_d2_s) ||
    !isNum(p.ratio) ||
    !Array.isArray(p.ratio_interval) ||
    p.ratio_interval.length !== 2 ||
    !p.ratio_interval.every(isNum)
  ) {
    fail('D2RunResult');
  }
  return {
    run_id: p.run_id,
    experiment_id: p.experiment_id,
    fuel: p.fuel,
    d0_mm: p.d0_mm,
    dext_mm: p.dext_mm,
    k_mm2_s: p.k_mm2_s,
    burn_time_s: p.burn_time_s,
    t_d2_s: p.t_d2_s,
    ratio: p.ratio,
    ratio_interval: [p.ratio_interval[0], p.ratio_interval[1]],
    review_flag: isStr(p.review_flag) ? p.review_flag : null,
  };
}

export function parseD2Consistency(p: unknown): D2ConsistencyResponse {
  if (!isObj(p)) fail('D2Consistency');
  if (
    p.analysis !== 'd2_consistency' ||
    !isStr(p.analysis_version) ||
    !isStr(p.equation) ||
    !isStr(p.value_origin) ||
    !isNum(p.n_runs) ||
    !isObj(p.excluded) ||
    !isObj(p.by_fuel) ||
    !strList(p.flagged_for_review) ||
    !Array.isArray(p.runs) ||
    !isObj(p.uncertainty) ||
    !strList(p.limitations)
  ) {
    fail('D2Consistency');
  }
  const by_fuel: Record<string, D2FuelSummary> = {};
  for (const [k, v] of Object.entries(p.by_fuel)) {
    by_fuel[k] = parseD2FuelSummary(v);
  }
  const runs = p.runs.map(parseD2RunResult);
  const excluded: Record<string, number> = {};
  for (const [k, v] of Object.entries(p.excluded)) {
    if (isNum(v)) excluded[k] = v;
  }
  return {
    analysis: 'd2_consistency',
    analysis_version: p.analysis_version,
    equation: p.equation,
    value_origin: p.value_origin,
    n_runs: p.n_runs,
    excluded,
    by_fuel,
    flagged_for_review: p.flagged_for_review,
    runs,
    uncertainty: {
      per_run: isStr((p.uncertainty as Obj).per_run) ? String((p.uncertainty as Obj).per_run) : '',
      summary: isStr((p.uncertainty as Obj).summary) ? String((p.uncertainty as Obj).summary) : '',
    },
    limitations: p.limitations,
  };
}

export function parseRegressionCoefficient(p: unknown): RegressionCoefficient {
  if (!isObj(p)) fail('RegressionCoefficient');
  if (
    !isNum(p.estimate) ||
    !isNum(p.se_hc3) ||
    !Array.isArray(p.ci95) ||
    p.ci95.length !== 2 ||
    !p.ci95.every(isNum) ||
    !isNum(p.p_value)
  ) {
    fail('RegressionCoefficient');
  }
  return {
    estimate: p.estimate,
    se_hc3: p.se_hc3,
    ci95: [p.ci95[0], p.ci95[1]],
    p_value: p.p_value,
  };
}

export function parseOlsModelResult(p: unknown): OlsModelResult {
  if (!isObj(p)) fail('OlsModelResult');
  if (!isNum(p.r_squared) || !isNum(p.dof_resid) || !isObj(p.intercept) || !isObj(p.x_o2)) {
    fail('OlsModelResult');
  }
  const intercept = parseRegressionCoefficient(p.intercept);
  const x_o2 = parseRegressionCoefficient(p.x_o2);
  let d0_mm: RegressionCoefficient | undefined;
  if ('d0_mm' in p && isObj(p.d0_mm)) {
    d0_mm = parseRegressionCoefficient(p.d0_mm);
  }
  return {
    intercept,
    x_o2,
    d0_mm,
    r_squared: p.r_squared,
    dof_resid: p.dof_resid,
  };
}

export function parseOxygenStratumResult(p: unknown): OxygenStratumResult {
  if (!isObj(p)) fail('OxygenStratumResult');
  if (
    !isStr(p.fuel) ||
    !isStr(p.support_mode) ||
    !isNum(p.n) ||
    !Array.isArray(p.x_o2_range) ||
    p.x_o2_range.length !== 2 ||
    !p.x_o2_range.every(isNum) ||
    !isNum(p.n_distinct_o2) ||
    !strList(p.run_ids) ||
    !isBool(p.computable)
  ) {
    fail('OxygenStratumResult');
  }
  const result: OxygenStratumResult = {
    fuel: p.fuel,
    pressure_cluster: isStr(p.pressure_cluster) ? p.pressure_cluster : null,
    support_mode: p.support_mode,
    n: p.n,
    x_o2_range: [p.x_o2_range[0], p.x_o2_range[1]],
    n_distinct_o2: p.n_distinct_o2,
    run_ids: p.run_ids,
    computable: p.computable,
  };
  if (isStr(p.abstention_reason)) {
    result.abstention_reason = p.abstention_reason;
  }
  if (p.model_k_on_o2 && isObj(p.model_k_on_o2)) {
    result.model_k_on_o2 = parseOlsModelResult(p.model_k_on_o2);
  }
  if (p.sensitivity_k_on_o2_and_d0 && isObj(p.sensitivity_k_on_o2_and_d0)) {
    result.sensitivity_k_on_o2_and_d0 = parseOlsModelResult(p.sensitivity_k_on_o2_and_d0);
  } else if (p.sensitivity_k_on_o2_and_d0 === null) {
    result.sensitivity_k_on_o2_and_d0 = null;
  }
  if (isNum(p.spearman_o2_k) || p.spearman_o2_k === null) {
    result.spearman_o2_k = p.spearman_o2_k;
  }
  return result;
}

export function parseOxygenEffect(p: unknown): OxygenEffectResponse {
  if (!isObj(p)) fail('OxygenEffect');
  if (
    p.analysis !== 'oxygen_effect' ||
    !isStr(p.analysis_version) ||
    !isStr(p.model) ||
    !isObj(p.units) ||
    !isStr(p.value_origin) ||
    !strList(p.strata_held_fixed) ||
    !isObj(p.excluded) ||
    !Array.isArray(p.strata) ||
    !strList(p.limitations)
  ) {
    fail('OxygenEffect');
  }
  const units: Record<string, string> = {};
  for (const [k, v] of Object.entries(p.units)) {
    if (isStr(v)) units[k] = v;
  }
  const excluded: Record<string, number> = {};
  for (const [k, v] of Object.entries(p.excluded)) {
    if (isNum(v)) excluded[k] = v;
  }
  const strata = p.strata.map(parseOxygenStratumResult);
  return {
    analysis: 'oxygen_effect',
    analysis_version: p.analysis_version,
    model: p.model,
    units,
    value_origin: p.value_origin,
    strata_held_fixed: p.strata_held_fixed,
    excluded,
    strata,
    limitations: p.limitations,
  };
}

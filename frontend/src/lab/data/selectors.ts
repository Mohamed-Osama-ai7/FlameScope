/**
 * Pure selectors for the Exploration Lab. No scientific calculation happens here:
 * eligibility comes from the Python v0.2.0 strata (record.eligible), statistics (rho) come from
 * dataset.strata. These functions only filter, group, count and order verified records.
 */
import type { AnalysisId, DiluentFamily, FlexRecord, Fuel, LabDataset, NumericField, SupportMode } from './types';
import { FIELD_LABEL, FUELS, SUPPORT_MODES } from './types';

// ------------------------------------------------------------------ visual filters

export interface Filters {
  fuels: Fuel[];
  supportModes: SupportMode[];
  families: DiluentFamily[];
  /** pressure cluster labels from the dataset, plus 'pressure_invalid' */
  clusters: string[];
  testEnds: string[];
  hideSensitivityRows: boolean;
}

export const PRESSURE_INVALID = 'pressure_invalid';

export function allOptions(records: FlexRecord[]) {
  const uniq = <T,>(xs: T[]) => [...new Set(xs)];
  return {
    fuels: FUELS.filter((f) => records.some((r) => r.fuel === f)),
    supportModes: SUPPORT_MODES.filter((s) => records.some((r) => r.support_mode === s)),
    families: uniq(records.map((r) => r.diluent_family)).sort() as DiluentFamily[],
    clusters: uniq(records.map((r) => r.pressure_cluster ?? PRESSURE_INVALID)).sort(clusterOrder),
    testEnds: uniq(records.map((r) => r.test_end)).sort(),
  };
}

/** Default view: every option selected except non-free-floating support modes (never pooled). */
export function defaultFilters(records: FlexRecord[]): Filters {
  const o = allOptions(records);
  return { ...o, supportModes: ['free_floating'], hideSensitivityRows: false };
}

export function clusterNominalAtm(label: string | null): number | null {
  if (!label) return null;
  const m = /^~([\d.]+) atm/.exec(label);
  return m ? Number(m[1]) : null;
}

function clusterOrder(a: string, b: string): number {
  return (clusterNominalAtm(a) ?? 99) - (clusterNominalAtm(b) ?? 99);
}

export type FilterReason = 'fuel' | 'support mode' | 'diluent family' | 'pressure cluster' | 'test end' | 'sensitivity rows hidden';

export function filterReason(r: FlexRecord, f: Filters): FilterReason | null {
  if (!f.fuels.includes(r.fuel)) return 'fuel';
  if (!f.supportModes.includes(r.support_mode)) return 'support mode';
  if (!f.families.includes(r.diluent_family)) return 'diluent family';
  if (!f.clusters.includes(r.pressure_cluster ?? PRESSURE_INVALID)) return 'pressure cluster';
  if (!f.testEnds.includes(r.test_end)) return 'test end';
  if (f.hideSensitivityRows && r.sensitivity_tags.length > 0) return 'sensitivity rows hidden';
  return null;
}

export interface FilterResult {
  included: FlexRecord[];
  excludedByFilter: Record<string, number>;
}

export function applyFilters(records: FlexRecord[], f: Filters): FilterResult {
  const included: FlexRecord[] = [];
  const excludedByFilter: Record<string, number> = {};
  for (const r of records) {
    const why = filterReason(r, f);
    if (why) excludedByFilter[why] = (excludedByFilter[why] ?? 0) + 1;
    else included.push(r);
  }
  return { included, excludedByFilter };
}

// ------------------------------------------------------------------ views (scientific eligibility)

export type ViewId =
  | 'k_o2'
  | 'k_pressure'
  | 'k_co2'
  | 'k_he'
  | 'k_d0'
  | 'k_dist'
  | 'cond_d0'
  | 'dext_o2'
  | 'cond_p_o2'
  | 'outcome_o2_d0';

export interface ViewDef {
  id: ViewId;
  title: string;
  question: string;
  x: NumericField | null;
  y: NumericField;
  /** Python v0.2.0 analysis whose strata define eligibility; null = the data rule stated in `rule`. */
  analysis: AnalysisId | null;
  rule: string;
  limitations: string[];
  colorBy: 'pressure_tier' | 'family' | 'test_end' | 'dext_class';
}

const SHARED_LIMITS = [
  'Observational, designed test matrix; no causal interpretation.',
  'K is the NASA-reported average burning-rate constant (FLEX team fit), not a FlameScope calculation; no K uncertainty is reported.',
];

export const VIEWS: Record<ViewId, ViewDef> = {
  k_o2: {
    id: 'k_o2', title: 'Reported K vs O₂ (N₂-only atmospheres)',
    question: 'How does the reported burning-rate constant vary with ambient O₂ when N₂ is the only balance gas?',
    x: 'ambient_oxygen_mole_fraction', y: 'burning_rate_constant_mm2_s', analysis: 'A1', colorBy: 'pressure_tier',
    rule: 'A1: N₂-only (CO₂ = He = 0), valid pressure and composition, reported K present.',
    limitations: [...SHARED_LIMITS, 'D₀, test date and pressure within a cluster also vary.'],
  },
  k_pressure: {
    id: 'k_pressure', title: 'Reported K vs ambient pressure (fixed O₂, N₂-only)',
    question: 'At a fixed O₂ level, does reported K differ between pressure levels?',
    x: 'ambient_pressure', y: 'burning_rate_constant_mm2_s', analysis: 'A4', colorBy: 'pressure_tier',
    rule: 'A4: N₂-only runs at one fixed O₂ value that spans at least two pressure clusters.',
    limitations: [...SHARED_LIMITS, 'Only O₂ = 0.30 meets the rule (n ≤ 4 per level): insufficient for any trend.',
      'The 2.03–3.05 atm records share one CO₂-rich composition and are not part of this rule (docs/11 §4).'],
  },
  k_co2: {
    id: 'k_co2', title: 'Reported K vs CO₂ (fixed-O₂ strata)',
    question: 'Within fixed-O₂ strata, how does reported K vary with added CO₂?',
    x: 'co2_mole_fraction', y: 'burning_rate_constant_mm2_s', analysis: 'A2', colorBy: 'pressure_tier',
    rule: 'A2: CO₂-added runs at a fixed O₂ value plus N₂-only reference runs at the same O₂, pressure cluster and support mode.',
    limitations: [...SHARED_LIMITS, 'Confounded: N₂ decreases as CO₂ increases; reference runs come from other test days.',
      'Points from different fixed-O₂ strata share these axes; compare within the strata table.'],
  },
  k_he: {
    id: 'k_he', title: 'Reported K vs He (fixed-O₂ strata)',
    question: 'Within fixed-O₂ strata, how does reported K vary with added He?',
    x: 'ambient_helium_mole_fraction', y: 'burning_rate_constant_mm2_s', analysis: 'A3', colorBy: 'pressure_tier',
    rule: 'A3: He-added runs at a fixed O₂ value plus N₂-only reference runs at the same O₂, pressure cluster and support mode.',
    limitations: [...SHARED_LIMITS, 'Confounded: N₂ decreases as He increases; strata are small.'],
  },
  k_d0: {
    id: 'k_d0', title: 'Reported K vs initial droplet diameter D₀',
    question: 'How is reported K distributed across D₀ within diluent family and pressure cluster?',
    x: 'initial_droplet_diameter', y: 'burning_rate_constant_mm2_s', analysis: 'A5', colorBy: 'family',
    rule: 'A5: reported K and D₀ present; stratified by fuel × diluent family × pressure cluster × support mode.',
    limitations: [...SHARED_LIMITS, 'UNRESOLVED / confounded: O₂ and diluent vary within strata (docs/11 §5).',
      'FLEX-001..009 used a 1/30 s shutter (D₀ at ignition ambiguous); see sensitivity ρ.'],
  },
  k_dist: {
    id: 'k_dist', title: 'Distribution of reported K by fuel and support mode',
    question: 'What range of reported K values occurs for each fuel and support regime?',
    x: null, y: 'burning_rate_constant_mm2_s', analysis: null, colorBy: 'pressure_tier',
    rule: 'All records with a reported K; every observation shown; groups never pooled across support modes.',
    limitations: [...SHARED_LIMITS, 'Conditions differ between records; a distribution is not a single-condition result.',
      'FLEX-130 (K = 0.05 mm²/s) is retained as reported (fiber-translated, very short burn).'],
  },
  cond_d0: {
    id: 'cond_d0', title: 'Distribution of initial droplet diameter D₀ by fuel and support mode',
    question: 'What range of initial droplet diameters was tested in each fuel and support regime?',
    x: null, y: 'initial_droplet_diameter', analysis: null, colorBy: 'pressure_tier',
    rule: 'All records with a valid D₀ (NASA Table IX "Actual D₀" at igniter-on).',
    limitations: ['FLEX-001..009: droplet size at ignition ambiguous (1/30 s shutter).',
      'Matrix Tables I–VIII list a differently defined "initial droplet diameter"; only Table IX D₀ is used.'],
  },
  dext_o2: {
    id: 'dext_o2', title: 'Visible flame extinction diameter vs O₂ (N₂-only, extinction runs)',
    question: 'Among eligible extinction runs, how does the reported extinction diameter vary with O₂?',
    x: 'ambient_oxygen_mole_fraction', y: 'extinction_diameter', analysis: 'A6', colorBy: 'pressure_tier',
    rule: 'A6: test end = Extinction, positive diameter, no extrapolation noted in the NASA caption, N₂-only, valid pressure.',
    limitations: [...SHARED_LIMITS.slice(0, 1), 'Confounded: extinction diameter depends on D₀, which also varies.',
      'Extrapolated diameters are listed in a separate table and are not part of A6.'],
  },
  cond_p_o2: {
    id: 'cond_p_o2', title: 'Experimental coverage: pressure × O₂',
    question: 'Which pressure and O₂ combinations were tested, by diluent family?',
    x: 'ambient_oxygen_mole_fraction', y: 'ambient_pressure', analysis: null, colorBy: 'family',
    rule: 'All records with valid pressure and O₂ (coverage view; no outcome variable).',
    limitations: ['H₂O and fuel-vapour fractions are not available; composition is incomplete and never normalised.',
      'FLEX-114 (0 mmHg) is invalid and not plotted; Table VI lists 0.70 atm (unresolved conflict).'],
  },
  outcome_o2_d0: {
    id: 'outcome_o2_d0', title: 'Test outcome by O₂ and D₀ (N₂-only)',
    question: 'How did tests end across the O₂ and D₀ that were tested?',
    x: 'ambient_oxygen_mole_fraction', y: 'initial_droplet_diameter', analysis: null, colorBy: 'test_end',
    rule: 'N₂-only records with valid O₂ and D₀; outcome categories exactly as reported by NASA.',
    limitations: ['Methanol disruption is attributed by NASA to needle-coating contamination (sec. 5.2); not an environmental response.',
      'NASA: no conclusion can be drawn on heptane disruption in these tests.'],
  },
};

export function isEligible(r: FlexRecord, v: ViewDef): boolean {
  if (v.analysis) return r.eligible.includes(v.analysis);
  if (v.id === 'outcome_o2_d0') return r.diluent_family === 'N2_only' && r.usable[v.y] && !!v.x && r.usable[v.x];
  return r.usable[v.y] && (!v.x || r.usable[v.x]);
}

/** Human-readable reason a record is outside a view's scientific rule (explanation only). */
export function ineligibleReason(r: FlexRecord, v: ViewDef): string {
  // Extinction-diameter views report NASA's semantic origin, never a merged 'missing' flag.
  if (v.id === 'dext_o2' && r.dext_origin !== 'reported_extinction_no_extrapolation_noted' && r.dext_origin !== 'reported_extinction_extrapolation_unknown') {
    return `extinction diameter: ${DEXT_CLASS[r.dext_origin] ?? r.dext_origin}`;
  }
  for (const f of [v.y, v.x]) {
    if (f && !r.usable[f]) {
      const flags = r.field_flags[f]?.join('+') ?? 'missing';
      return `${FIELD_LABEL[f]}: ${flags}`;
    }
  }
  if ((v.id === 'k_o2' || v.id === 'k_pressure' || v.id === 'dext_o2' || v.id === 'outcome_o2_d0') && r.diluent_family !== 'N2_only') return 'not N₂-only';
  return v.analysis ? `outside ${v.analysis} strata (see rule)` : 'outside view rule';
}

export interface ViewData {
  view: ViewDef;
  eligible: FlexRecord[];
  ineligible: Record<string, number>;
  shown: FlexRecord[];
  excludedByFilter: Record<string, number>;
  panels: { fuel: Fuel; support: SupportMode; records: FlexRecord[] }[];
}

export function viewData(records: FlexRecord[], v: ViewDef, f: Filters): ViewData {
  const eligible: FlexRecord[] = [];
  const ineligible: Record<string, number> = {};
  for (const r of records) {
    if (isEligible(r, v)) eligible.push(r);
    else {
      const why = ineligibleReason(r, v);
      ineligible[why] = (ineligible[why] ?? 0) + 1;
    }
  }
  const { included: shown, excludedByFilter } = applyFilters(eligible, f);
  const panels: ViewData['panels'] = [];
  for (const support of SUPPORT_MODES.filter((s) => f.supportModes.includes(s))) {
    for (const fuel of FUELS.filter((x) => f.fuels.includes(x))) {
      panels.push({ fuel, support, records: shown.filter((r) => r.fuel === fuel && r.support_mode === support) });
    }
  }
  return { view: v, eligible, ineligible, shown, excludedByFilter, panels };
}

// ------------------------------------------------------------------ encodings (display groupings only)

export function pressureTier(r: FlexRecord): string {
  const atm = clusterNominalAtm(r.pressure_cluster);
  if (atm === null) return 'pressure invalid';
  if (atm < 0.85) return '≈0.7 atm';
  if (atm < 1.5) return '≈1.0 atm';
  return '2.03–3.05 atm';
}
export const PRESSURE_TIERS = ['≈0.7 atm', '≈1.0 atm', '2.03–3.05 atm'];

export const DEXT_CLASS: Record<string, string> = {
  reported_extinction_no_extrapolation_noted: 'Reported, no extrapolation noted',
  reported_extinction_extrapolation_noted_in_caption: 'Extrapolated (NASA caption)',
  reported_extinction_extrapolation_unknown: 'Reported, extrapolation status unknown',
  not_applicable_no_extinction_per_A1: "No finite-size extinction: completion or disruption (NASA '–')",
  not_listed_insufficient_view_per_A1: 'Not listed: insufficient HiBMs observation history',
  inconsistent_dash_with_extinction_end: "Conflicting: '–' with test end Extinction",
  zero_semantics_unconfirmed: 'Zero value: meaning unconfirmed',
  value_with_non_extinction_end_semantics_unclear: 'Value with completion/disruption end: meaning unclear',
};

export function groupOf(r: FlexRecord, colorBy: ViewDef['colorBy']): string {
  switch (colorBy) {
    case 'pressure_tier': return pressureTier(r);
    case 'family': return r.diluent_family;
    case 'test_end': return r.test_end;
    case 'dext_class': return r.dext_origin === 'reported_extinction_extrapolation_noted_in_caption' ? 'Extrapolated (not in A6)' : 'Eligible (A6)';
  }
}

// ------------------------------------------------------------------ counts, coverage, distributions

export function countBy<T>(xs: T[], key: (x: T) => string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const x of xs) out[key(x)] = (out[key(x)] ?? 0) + 1;
  return out;
}

export function ecdf(values: number[]): { x: number[]; y: number[] } {
  const x = [...values].sort((a, b) => a - b);
  return { x, y: x.map((_, i) => (i + 1) / x.length) };
}

export function strataFor(d: LabDataset, analysis: AnalysisId, supportModes: SupportMode[], fuels: Fuel[]) {
  return d.strata.filter(
    (s) => s.analysis.startsWith(`${analysis}_`) && fuels.includes(s.fuel) &&
      supportModes.includes(String(s.stratum.support_mode) as SupportMode),
  );
}

// ------------------------------------------------------------------ data-quality warnings (no composite scores)

export interface Warning {
  rule: string;
  label: string;
  field?: NumericField;
  recordKeys: string[];
}

export function qualityWarnings(d: LabDataset): Warning[] {
  const map = new Map<string, Warning>();
  const add = (rule: string, label: string, key: string | null, field?: NumericField) => {
    const id = `${rule}|${field ?? ''}`;
    const w = map.get(id) ?? { rule, label, field, recordKeys: [] };
    if (key) w.recordKeys.push(key);
    map.set(id, w);
  };
  for (const r of d.records) {
    for (const [field, flags] of Object.entries(r.field_flags) as [NumericField, string[]][]) {
      for (const flag of flags) add(`quality.${flag}`, `${FIELD_LABEL[field]}: ${flag.replaceAll('_', ' ')}`, r.record_key, field);
    }
    for (const flag of r.row_flags) add(`quality.${flag}`, flag.replaceAll('_', ' '), r.record_key);
    for (const tag of r.sensitivity_tags) add(`evidence.${tag}`, tag.replaceAll('_', ' '), r.record_key);
    if (r.support_mode === 'conflicting_sources') add('evidence.conflicting_sources', 'support mode: conflicting sources', r.record_key);
    if (r.evidence.pressure_source_conflict) add('evidence.pressure_source_conflict', 'pressure: source conflict', r.record_key);
    if (r.evidence.documented_contamination_or_feature) add('evidence.coated_needle_period', `documented: ${r.evidence.documented_contamination_or_feature}`, r.record_key);
  }
  add('evidence.unmapped_tests', 'Table IX rows not in PSI-69 (FLEX-216, FLEX-230); 284 stated vs 276 printed vs 274 records', null);
  add('evidence.missing_composition', 'H₂O and fuel-vapour mole fractions unavailable (composition incomplete)', null);
  return [...map.values()].sort((a, b) => a.rule.localeCompare(b.rule) || a.label.localeCompare(b.label));
}

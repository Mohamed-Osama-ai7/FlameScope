import type { LabDataset } from './types';

export const DATASET_URL = `${import.meta.env.BASE_URL}data/flex_lab_dataset_v0.2.0.json`;
export const EXPECTED_ANALYSIS_VERSION = '0.2.0';

export class DatasetError extends Error {}

/** Structural checks only; scientific values come verified from the Python export. */
export function validateDataset(d: LabDataset, opts: { allowSynthetic?: boolean } = {}): LabDataset {
  if (d.synthetic && !opts.allowSynthetic) {
    throw new DatasetError('Synthetic test data cannot be loaded into the scientific lab.');
  }
  if (!d.synthetic && d.analysis_version !== EXPECTED_ANALYSIS_VERSION) {
    throw new DatasetError(`Expected analysis ${EXPECTED_ANALYSIS_VERSION}, got ${d.analysis_version}`);
  }
  if (!Array.isArray(d.records) || d.records.length !== d.scope.records) {
    throw new DatasetError('Record count does not match dataset scope.');
  }
  const keys = new Set(d.records.map((r) => r.record_key));
  if (keys.size !== d.records.length) throw new DatasetError('Record keys are not unique.');
  if (!d.synthetic && !/^[0-9a-f]{64}$/.test(d.provenance.raw_sha256)) {
    throw new DatasetError('Missing raw SHA-256 provenance.');
  }
  return d;
}

export async function loadDataset(url = DATASET_URL): Promise<LabDataset> {
  const res = await fetch(url);
  if (!res.ok) throw new DatasetError(`Dataset request failed: ${res.status}`);
  return validateDataset((await res.json()) as LabDataset);
}

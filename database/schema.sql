-- Initial relational schema. This is a starting contract, not a claim that the source datasets
-- contain every field. Populate only fields verified in the acquired source artifacts.
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_repository TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_version TEXT,
    doi TEXT,
    license_id TEXT,
    flight_platform TEXT,
    retrieved_at TIMESTAMPTZ,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id UUID PRIMARY KEY,
    investigation_id TEXT REFERENCES investigations(investigation_id),
    file_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    media_type TEXT,
    byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
    sha256 CHAR(64) NOT NULL,
    source_url TEXT NOT NULL,
    source_version TEXT,
    license_id TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (relative_path, sha256)
);

CREATE TABLE IF NOT EXISTS experimental_runs (
    run_id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
    artifact_id UUID REFERENCES source_artifacts(artifact_id),
    combustion_regime TEXT NOT NULL
        CHECK (combustion_regime IN ('flex_droplet', 'bass_ii_solid', 'saffire_spacecraft_scale')),
    material_or_fuel TEXT,
    apparatus TEXT,
    gravity_level_g DOUBLE PRECISION,
    pressure_value DOUBLE PRECISION,
    pressure_unit TEXT,
    conditions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Outcomes live in measurements (one row per variable); no denormalised outcome_* columns,
    -- so a run cannot carry an outcome without unit, locator and extraction method.
    source_locator TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS measurements (
    measurement_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES experimental_runs(run_id),
    artifact_id UUID REFERENCES source_artifacts(artifact_id),
    variable_name TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    timestamp_value DOUBLE PRECISION,
    timestamp_unit TEXT,
    uncertainty_value DOUBLE PRECISION CHECK (uncertainty_value IS NULL OR uncertainty_value >= 0),
    uncertainty_type TEXT,          -- e.g. 'standard_1sigma', 'expanded', 'reported_range'
    coverage_factor DOUBLE PRECISION,
    measured_or_derived TEXT NOT NULL DEFAULT 'measured'
        CHECK (measured_or_derived IN ('measured', 'derived', 'report_value')),
    sensor_or_method TEXT,
    calibration_status TEXT,
    source_locator TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    quality_flags JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- Every computed result references the method card version and the exact input measurements.
CREATE TABLE IF NOT EXISTS analysis_results (
    result_id UUID PRIMARY KEY,
    method_id TEXT NOT NULL,
    method_version TEXT NOT NULL,
    run_id TEXT REFERENCES experimental_runs(run_id),
    input_measurement_ids BIGINT[] NOT NULL,
    computable BOOLEAN NOT NULL,
    abstention_reason TEXT,
    output_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (computable OR abstention_reason IS NOT NULL)
);

-- Text corpus for retrieval (populated only from registered source_artifacts).
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES source_artifacts(artifact_id),
    investigation_id TEXT REFERENCES investigations(investigation_id),
    combustion_regime TEXT,
    page_or_section TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    UNIQUE (artifact_id, chunker_version, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_runs_investigation ON experimental_runs(investigation_id);
CREATE INDEX IF NOT EXISTS idx_runs_regime ON experimental_runs(combustion_regime);
CREATE INDEX IF NOT EXISTS idx_measurements_run_variable ON measurements(run_id, variable_name);
CREATE INDEX IF NOT EXISTS idx_artifacts_investigation ON source_artifacts(investigation_id);

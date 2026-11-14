-- FlameScope scientific database schema (PostgreSQL 16).
-- GENERATED FILE - do not edit by hand. Source of truth: backend/app/data_platform/models.py and the
-- Alembic migrations in backend/app/data_platform/migrations/versions/. Regenerate from backend/ with:
--   alembic upgrade head --sql > ../database/schema.sql   (then re-add this header)
-- Apply to a database with `alembic upgrade head`, not with this file, so the revision is tracked.

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE investigations (
    investigation_id VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    acronym VARCHAR(64),
    combustion_regime VARCHAR(64) NOT NULL,
    source_repository TEXT NOT NULL,
    source_url TEXT NOT NULL,
    doi VARCHAR(128),
    license_id VARCHAR(64),
    research_area VARCHAR(128),
    official_challenge_resource BOOLEAN NOT NULL,
    registry_status VARCHAR(32) NOT NULL,
    metadata_json JSONB DEFAULT '{}' NOT NULL,
    CONSTRAINT pk_investigations PRIMARY KEY (investigation_id),
    CONSTRAINT ck_investigations_regime CHECK (combustion_regime IN ('flex_droplet', 'bass_ii_solid', 'saffire_spacecraft_scale'))
);

CREATE TABLE units (
    symbol VARCHAR(32) NOT NULL,
    dimension VARCHAR(32) NOT NULL,
    CONSTRAINT pk_units PRIMARY KEY (symbol),
    CONSTRAINT ck_units_dimension CHECK (dimension IN ('length', 'length^2/time', 'length/time', 'time', 'pressure', 'dimensionless', 'g_ratio'))
);

CREATE TABLE variables (
    name VARCHAR(128) NOT NULL,
    dimension VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    environmental BOOLEAN NOT NULL,
    defined_in VARCHAR(128) NOT NULL,
    CONSTRAINT pk_variables PRIMARY KEY (name),
    CONSTRAINT ck_variables_dimension CHECK (dimension IN ('length', 'length^2/time', 'length/time', 'time', 'pressure', 'dimensionless', 'g_ratio'))
);

CREATE TABLE source_artifacts (
    artifact_id UUID NOT NULL,
    investigation_id VARCHAR(64) NOT NULL,
    artifact_kind VARCHAR(64) NOT NULL,
    file_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    media_type VARCHAR(128),
    text_encoding VARCHAR(32),
    byte_size BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    source_url TEXT NOT NULL,
    source_version TEXT,
    license_id VARCHAR(64),
    retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata_json JSONB DEFAULT '{}' NOT NULL,
    CONSTRAINT pk_source_artifacts PRIMARY KEY (artifact_id),
    CONSTRAINT ck_source_artifacts_byte_size_nonnegative CHECK (byte_size >= 0),
    CONSTRAINT ck_source_artifacts_sha256_length CHECK (length(sha256) = 64),
    CONSTRAINT fk_source_artifacts_investigation_id_investigations FOREIGN KEY(investigation_id) REFERENCES investigations (investigation_id),
    CONSTRAINT uq_source_artifacts_path_sha256 UNIQUE (relative_path, sha256)
);

CREATE INDEX ix_source_artifacts_investigation_id ON source_artifacts (investigation_id);

CREATE TABLE document_chunks (
    chunk_id UUID NOT NULL,
    artifact_id UUID NOT NULL,
    investigation_id VARCHAR(64),
    combustion_regime VARCHAR(64),
    page_or_section TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    chunker_version VARCHAR(32) NOT NULL,
    CONSTRAINT pk_document_chunks PRIMARY KEY (chunk_id),
    CONSTRAINT fk_document_chunks_artifact_id_source_artifacts FOREIGN KEY(artifact_id) REFERENCES source_artifacts (artifact_id),
    CONSTRAINT fk_document_chunks_investigation_id_investigations FOREIGN KEY(investigation_id) REFERENCES investigations (investigation_id),
    CONSTRAINT uq_document_chunks_artifact_version_index UNIQUE (artifact_id, chunker_version, chunk_index)
);

CREATE TABLE extraction_runs (
    extraction_run_id UUID NOT NULL,
    artifact_id UUID NOT NULL,
    extractor_name VARCHAR(128) NOT NULL,
    extractor_version VARCHAR(32) NOT NULL,
    inputs_json JSONB NOT NULL,
    parameters_json JSONB DEFAULT '{}' NOT NULL,
    code_revision VARCHAR(64),
    run_count INTEGER NOT NULL,
    measurement_count INTEGER NOT NULL,
    first_loaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    last_loaded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_extraction_runs PRIMARY KEY (extraction_run_id),
    CONSTRAINT ck_extraction_runs_counts_nonnegative CHECK (run_count >= 0 AND measurement_count >= 0),
    CONSTRAINT fk_extraction_runs_artifact_id_source_artifacts FOREIGN KEY(artifact_id) REFERENCES source_artifacts (artifact_id)
);

CREATE INDEX ix_extraction_runs_artifact_id ON extraction_runs (artifact_id);

CREATE TABLE data_quality_checks (
    check_id UUID NOT NULL,
    extraction_run_id UUID NOT NULL,
    check_name VARCHAR(128) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    outcome VARCHAR(16) NOT NULL,
    affected_count INTEGER NOT NULL,
    description TEXT NOT NULL,
    details_json JSONB DEFAULT '{}' NOT NULL,
    CONSTRAINT pk_data_quality_checks PRIMARY KEY (check_id),
    CONSTRAINT ck_data_quality_checks_outcome CHECK (outcome IN ('pass', 'fail', 'flagged')),
    CONSTRAINT ck_data_quality_checks_severity CHECK (severity IN ('error', 'warning', 'info')),
    CONSTRAINT ck_data_quality_checks_affected_count_nonnegative CHECK (affected_count >= 0),
    CONSTRAINT fk_data_quality_checks_extraction_run_id_extraction_runs FOREIGN KEY(extraction_run_id) REFERENCES extraction_runs (extraction_run_id) ON DELETE CASCADE,
    CONSTRAINT uq_data_quality_checks_run_check UNIQUE (extraction_run_id, check_name)
);

CREATE TABLE experimental_runs (
    run_id VARCHAR(64) NOT NULL,
    investigation_id VARCHAR(64) NOT NULL,
    artifact_id UUID NOT NULL,
    extraction_run_id UUID NOT NULL,
    source_row INTEGER NOT NULL,
    source_identifier VARCHAR(128) NOT NULL,
    source_record_key VARCHAR(256),
    combustion_regime VARCHAR(64) NOT NULL,
    material_or_fuel VARCHAR(256),
    test_date DATE,
    test_date_raw VARCHAR(32) NOT NULL,
    test_time_gmt_raw VARCHAR(32) NOT NULL,
    end_mode VARCHAR(64),
    apparatus TEXT,
    gravity_level_g FLOAT,
    source_locator TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    quality_flags JSONB DEFAULT '[]' NOT NULL,
    derived_attributes JSONB DEFAULT '{}' NOT NULL,
    CONSTRAINT pk_experimental_runs PRIMARY KEY (run_id),
    CONSTRAINT ck_experimental_runs_regime CHECK (combustion_regime IN ('flex_droplet', 'bass_ii_solid', 'saffire_spacecraft_scale')),
    CONSTRAINT ck_experimental_runs_source_row_positive CHECK (source_row >= 1),
    CONSTRAINT fk_experimental_runs_artifact_id_source_artifacts FOREIGN KEY(artifact_id) REFERENCES source_artifacts (artifact_id),
    CONSTRAINT fk_experimental_runs_extraction_run_id_extraction_runs FOREIGN KEY(extraction_run_id) REFERENCES extraction_runs (extraction_run_id),
    CONSTRAINT fk_experimental_runs_investigation_id_investigations FOREIGN KEY(investigation_id) REFERENCES investigations (investigation_id),
    CONSTRAINT uq_experimental_runs_artifact_row UNIQUE (artifact_id, source_row),
    CONSTRAINT uq_experimental_runs_source_record_key UNIQUE (source_record_key)
);

CREATE INDEX ix_experimental_runs_combustion_regime ON experimental_runs (combustion_regime);

CREATE INDEX ix_experimental_runs_investigation_id ON experimental_runs (investigation_id);

CREATE INDEX ix_experimental_runs_source_identifier ON experimental_runs (source_identifier);

CREATE TABLE analysis_results (
    result_id UUID NOT NULL,
    method_id VARCHAR(128) NOT NULL,
    method_version VARCHAR(32) NOT NULL,
    run_id VARCHAR(64),
    computable BOOLEAN NOT NULL,
    abstention_reason TEXT,
    output_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_analysis_results PRIMARY KEY (result_id),
    CONSTRAINT ck_analysis_results_abstention_reason CHECK (computable OR abstention_reason IS NOT NULL),
    CONSTRAINT fk_analysis_results_run_id_experimental_runs FOREIGN KEY(run_id) REFERENCES experimental_runs (run_id)
);

CREATE TABLE measurements (
    measurement_id UUID NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    artifact_id UUID NOT NULL,
    extraction_run_id UUID NOT NULL,
    variable_name VARCHAR(128) NOT NULL,
    role VARCHAR(16) NOT NULL,
    value FLOAT,
    value_status VARCHAR(16) NOT NULL,
    original_value_text TEXT NOT NULL,
    unit VARCHAR(32) NOT NULL,
    original_unit_label VARCHAR(64),
    unit_evidence TEXT,
    timestamp_value FLOAT,
    timestamp_unit VARCHAR(32),
    uncertainty_value FLOAT,
    uncertainty_type VARCHAR(64),
    coverage_factor FLOAT,
    measured_or_derived VARCHAR(16) NOT NULL,
    sensor_or_method TEXT,
    calibration_status VARCHAR(64),
    source_row INTEGER NOT NULL,
    source_column TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    usable_for_analysis BOOLEAN NOT NULL,
    quality_flags JSONB DEFAULT '[]' NOT NULL,
    attributes JSONB DEFAULT '{}' NOT NULL,
    CONSTRAINT pk_measurements PRIMARY KEY (measurement_id),
    CONSTRAINT ck_measurements_value_matches_status CHECK ((value IS NULL AND value_status IN ('missing', 'unparseable')) OR (value IS NOT NULL AND value_status IN ('parsed', 'approximate'))),
    CONSTRAINT ck_measurements_measured_or_derived CHECK (measured_or_derived IN ('measured', 'derived', 'report_value')),
    CONSTRAINT ck_measurements_role CHECK (role IN ('condition', 'outcome')),
    CONSTRAINT ck_measurements_value_status CHECK (value_status IN ('parsed', 'approximate', 'missing', 'unparseable')),
    CONSTRAINT ck_measurements_usable_requires_value CHECK (NOT usable_for_analysis OR value IS NOT NULL),
    CONSTRAINT ck_measurements_source_row_positive CHECK (source_row >= 1),
    CONSTRAINT ck_measurements_uncertainty_nonnegative CHECK (uncertainty_value IS NULL OR uncertainty_value >= 0),
    CONSTRAINT fk_measurements_artifact_id_source_artifacts FOREIGN KEY(artifact_id) REFERENCES source_artifacts (artifact_id),
    CONSTRAINT fk_measurements_extraction_run_id_extraction_runs FOREIGN KEY(extraction_run_id) REFERENCES extraction_runs (extraction_run_id),
    CONSTRAINT fk_measurements_run_id_experimental_runs FOREIGN KEY(run_id) REFERENCES experimental_runs (run_id),
    CONSTRAINT fk_measurements_unit_units FOREIGN KEY(unit) REFERENCES units (symbol),
    CONSTRAINT fk_measurements_variable_name_variables FOREIGN KEY(variable_name) REFERENCES variables (name),
    CONSTRAINT uq_measurements_cell UNIQUE (artifact_id, source_row, source_column)
);

CREATE INDEX ix_measurements_run_variable ON measurements (run_id, variable_name);

CREATE INDEX ix_measurements_variable_name ON measurements (variable_name);

CREATE TABLE analysis_result_inputs (
    result_id UUID NOT NULL,
    measurement_id UUID NOT NULL,
    CONSTRAINT pk_analysis_result_inputs PRIMARY KEY (result_id, measurement_id),
    CONSTRAINT fk_analysis_result_inputs_measurement_id_measurements FOREIGN KEY(measurement_id) REFERENCES measurements (measurement_id) ON DELETE RESTRICT,
    CONSTRAINT fk_analysis_result_inputs_result_id_analysis_results FOREIGN KEY(result_id) REFERENCES analysis_results (result_id) ON DELETE CASCADE
);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;


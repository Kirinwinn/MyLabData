-- MyLabData MLD2 DryData registry schema, version 1.
-- Large molecule attributes remain in Parquet; this database stores identity,
-- provenance, import history, and query caches.

CREATE SEQUENCE IF NOT EXISTS source_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS molecule_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS attribute_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS import_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS distribution_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS stat_id_seq START 1;

CREATE TABLE IF NOT EXISTS Sources (
    source_id BIGINT PRIMARY KEY DEFAULT nextval('source_id_seq'),
    source_key VARCHAR NOT NULL UNIQUE,
    source_name VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL CHECK (
        source_type IN ('external', 'generated', 'derived', 'manual', 'system')
    ),
    source_uri VARCHAR,
    description VARCHAR,
    metadata JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    is_active BOOLEAN NOT NULL DEFAULT true,
    CHECK (length(trim(source_key)) > 0),
    CHECK (length(trim(source_name)) > 0)
);

CREATE TABLE IF NOT EXISTS Molecules (
    molecule_id BIGINT PRIMARY KEY DEFAULT nextval('molecule_id_seq'),
    lab_id VARCHAR UNIQUE,
    canonical_smiles VARCHAR NOT NULL UNIQUE,
    inchikey VARCHAR UNIQUE,
    original_smiles VARCHAR,
    primary_source_id BIGINT REFERENCES Sources(source_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    is_active BOOLEAN NOT NULL DEFAULT true,
    CHECK (length(trim(canonical_smiles)) > 0)
);

CREATE TABLE IF NOT EXISTS Attributes (
    attribute_id BIGINT PRIMARY KEY DEFAULT nextval('attribute_id_seq'),
    attribute_key VARCHAR NOT NULL UNIQUE,
    attribute_name VARCHAR NOT NULL,
    attribute_category VARCHAR NOT NULL CHECK (
        attribute_category IN ('trait', 'prediction', 'annotation')
    ),
    value_type VARCHAR NOT NULL CHECK (
        value_type IN ('float', 'integer', 'boolean', 'string', 'json')
    ),
    unit VARCHAR,
    description VARCHAR,
    model_name VARCHAR,
    model_version VARCHAR,
    source_id BIGINT REFERENCES Sources(source_id),
    metadata JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    is_active BOOLEAN NOT NULL DEFAULT true,
    CHECK (length(trim(attribute_key)) > 0),
    CHECK (length(trim(attribute_name)) > 0)
);

CREATE TABLE IF NOT EXISTS Imports (
    import_id BIGINT PRIMARY KEY DEFAULT nextval('import_id_seq'),
    source_id BIGINT NOT NULL REFERENCES Sources(source_id),
    data_category VARCHAR NOT NULL CHECK (
        data_category IN ('molecules', 'traits', 'predictions', 'annotations')
    ),
    source_class VARCHAR NOT NULL CHECK (
        source_class IN ('external', 'generated', 'derived', 'manual')
    ),
    original_filename VARCHAR NOT NULL,
    input_path VARCHAR NOT NULL,
    processed_path VARCHAR,
    file_format VARCHAR NOT NULL CHECK (
        file_format IN ('csv', 'parquet', 'xlsx', 'db', 'sdf', 'other')
    ),
    checksum_sha256 VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'queued' CHECK (
        status IN ('queued', 'processing', 'completed', 'failed')
    ),
    total_rows BIGINT CHECK (total_rows IS NULL OR total_rows >= 0),
    accepted_rows BIGINT CHECK (accepted_rows IS NULL OR accepted_rows >= 0),
    rejected_rows BIGINT CHECK (rejected_rows IS NULL OR rejected_rows >= 0),
    duplicate_rows BIGINT CHECK (duplicate_rows IS NULL OR duplicate_rows >= 0),
    processor_name VARCHAR,
    processor_version VARCHAR,
    attribute_keys JSON,
    metadata JSON,
    error_message VARCHAR,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    CHECK (length(trim(original_filename)) > 0),
    CHECK (length(trim(input_path)) > 0)
);

CREATE TABLE IF NOT EXISTS AttributeDistributions (
    distribution_id BIGINT PRIMARY KEY DEFAULT nextval('distribution_id_seq'),
    attribute_id BIGINT NOT NULL REFERENCES Attributes(attribute_id),
    scope_hash VARCHAR NOT NULL,
    scope_definition JSON,
    data_revision VARCHAR NOT NULL,
    distribution_type VARCHAR NOT NULL CHECK (
        distribution_type IN ('histogram', 'categories')
    ),
    bin_edges JSON,
    bin_counts JSON,
    category_counts JSON,
    non_null_count BIGINT NOT NULL CHECK (non_null_count >= 0),
    null_count BIGINT NOT NULL CHECK (null_count >= 0),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    expires_at TIMESTAMPTZ,
    UNIQUE (attribute_id, scope_hash, data_revision)
);

CREATE TABLE IF NOT EXISTS AttributeStats (
    stat_id BIGINT PRIMARY KEY DEFAULT nextval('stat_id_seq'),
    attribute_id BIGINT NOT NULL REFERENCES Attributes(attribute_id),
    scope_hash VARCHAR NOT NULL,
    scope_definition JSON,
    data_revision VARCHAR NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    non_null_count BIGINT NOT NULL CHECK (non_null_count >= 0),
    null_count BIGINT NOT NULL CHECK (null_count >= 0),
    distinct_count BIGINT CHECK (distinct_count IS NULL OR distinct_count >= 0),
    min_value DOUBLE,
    max_value DOUBLE,
    mean_value DOUBLE,
    stddev_value DOUBLE,
    median_value DOUBLE,
    q1_value DOUBLE,
    q3_value DOUBLE,
    min_text VARCHAR,
    max_text VARCHAR,
    top_values JSON,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    expires_at TIMESTAMPTZ,
    UNIQUE (attribute_id, scope_hash, data_revision)
);

CREATE INDEX IF NOT EXISTS idx_sources_type ON Sources(source_type);
CREATE INDEX IF NOT EXISTS idx_molecules_inchikey ON Molecules(inchikey);
CREATE INDEX IF NOT EXISTS idx_molecules_source ON Molecules(primary_source_id);
CREATE INDEX IF NOT EXISTS idx_attributes_category ON Attributes(attribute_category);
CREATE INDEX IF NOT EXISTS idx_attributes_source ON Attributes(source_id);
CREATE INDEX IF NOT EXISTS idx_imports_status ON Imports(status);
CREATE INDEX IF NOT EXISTS idx_imports_source ON Imports(source_id);
CREATE INDEX IF NOT EXISTS idx_distributions_attribute ON AttributeDistributions(attribute_id);
CREATE INDEX IF NOT EXISTS idx_stats_attribute ON AttributeStats(attribute_id);

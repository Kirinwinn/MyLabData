-- MyLabData v2 initial DuckDB business schema.

CREATE SEQUENCE molecule_id_seq START WITH 1;
CREATE SEQUENCE attribute_id_seq START WITH 1;
CREATE SEQUENCE entry_id_seq START WITH 1;
CREATE SEQUENCE source_id_seq START WITH 1;
CREATE SEQUENCE import_id_seq START WITH 1;

CREATE TABLE Molecules (
    molecule_id BIGINT PRIMARY KEY DEFAULT nextval('molecule_id_seq'),
    lab_id VARCHAR NOT NULL UNIQUE,
    canonical_smiles VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(lab_id)) > 0),
    CHECK (length(trim(canonical_smiles)) > 0)
);

CREATE TABLE Attributes (
    attribute_id BIGINT PRIMARY KEY DEFAULT nextval('attribute_id_seq'),
    attribute_key VARCHAR NOT NULL UNIQUE,
    attribute_name VARCHAR NOT NULL,
    value_type VARCHAR NOT NULL,
    unit VARCHAR,
    description VARCHAR,
    CHECK (regexp_full_match(attribute_key, '[a-z][a-z0-9_]*')),
    CHECK (length(trim(attribute_name)) > 0),
    CHECK (value_type IN ('number', 'text', 'boolean')),
    CHECK (unit IS NULL OR length(trim(unit)) > 0)
);

CREATE TABLE Sources (
    source_id BIGINT PRIMARY KEY DEFAULT nextval('source_id_seq'),
    source_key VARCHAR NOT NULL UNIQUE,
    source_name VARCHAR NOT NULL,
    source_type VARCHAR NOT NULL,
    description VARCHAR,
    CHECK (regexp_full_match(source_key, '[a-z][a-z0-9_.-]*')),
    CHECK (length(trim(source_name)) > 0),
    CHECK (length(trim(source_type)) > 0)
);

CREATE TABLE Entries (
    entry_id BIGINT PRIMARY KEY DEFAULT nextval('entry_id_seq'),
    attribute_id BIGINT NOT NULL REFERENCES Attributes(attribute_id),
    entry_key VARCHAR NOT NULL UNIQUE,
    annotation_kind VARCHAR NOT NULL,
    method_name VARCHAR NOT NULL,
    method_version VARCHAR,
    conditions_json JSON NOT NULL DEFAULT '{}',
    source_id BIGINT REFERENCES Sources(source_id),
    is_mutable BOOLEAN NOT NULL DEFAULT false,
    description VARCHAR,
    CHECK (regexp_full_match(entry_key, '[a-z][a-z0-9_]*([.][a-z0-9_]+)*')),
    CHECK (annotation_kind IN ('prediction', 'calculation', 'property')),
    CHECK (length(trim(method_name)) > 0),
    CHECK (method_version IS NULL OR length(trim(method_version)) > 0),
    CHECK (json_type(conditions_json) = 'OBJECT'),
    CHECK (annotation_kind = 'property' OR is_mutable = false)
);

CREATE TABLE Annotations (
    molecule_id BIGINT NOT NULL REFERENCES Molecules(molecule_id),
    entry_id BIGINT NOT NULL REFERENCES Entries(entry_id),
    value_number DOUBLE,
    value_text VARCHAR,
    value_boolean BOOLEAN,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (molecule_id, entry_id),
    CHECK (
        (CASE WHEN value_number IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN value_boolean IS NOT NULL THEN 1 ELSE 0 END) = 1
    ),
    CHECK (updated_at >= created_at)
);

CREATE TABLE Imports (
    import_id BIGINT PRIMARY KEY DEFAULT nextval('import_id_seq'),
    source_id BIGINT REFERENCES Sources(source_id),
    file_name VARCHAR NOT NULL,
    file_hash VARCHAR NOT NULL,
    data_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    processor_name VARCHAR,
    total_rows BIGINT NOT NULL DEFAULT 0,
    accepted_rows BIGINT NOT NULL DEFAULT 0,
    failed_rows BIGINT NOT NULL DEFAULT 0,
    error_message VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    CHECK (length(trim(file_name)) > 0),
    CHECK (length(trim(file_hash)) > 0),
    CHECK (data_type IN ('molecules', 'annotations')),
    CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    CHECK (processor_name IS NULL OR length(trim(processor_name)) > 0),
    CHECK (total_rows >= 0),
    CHECK (accepted_rows >= 0),
    CHECK (failed_rows >= 0),
    CHECK (accepted_rows + failed_rows <= total_rows),
    CHECK (finished_at IS NULL OR finished_at >= created_at)
);

CREATE TABLE AttributeDistributions (
    attribute_id BIGINT NOT NULL REFERENCES Attributes(attribute_id),
    scope_definition JSON NOT NULL,
    distribution_data JSON NOT NULL,
    data_revision BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (json_type(scope_definition) = 'OBJECT'),
    CHECK (data_revision >= 0)
);

CREATE TABLE AttributeStats (
    attribute_id BIGINT NOT NULL REFERENCES Attributes(attribute_id),
    entry_id BIGINT NOT NULL REFERENCES Entries(entry_id),
    count BIGINT NOT NULL,
    null_count BIGINT NOT NULL,
    min DOUBLE,
    max DOUBLE,
    mean DOUBLE,
    median DOUBLE,
    std DOUBLE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (attribute_id, entry_id),
    CHECK (count >= 0),
    CHECK (null_count >= 0),
    CHECK (null_count <= count),
    CHECK (min IS NULL OR max IS NULL OR min <= max),
    CHECK (std IS NULL OR std >= 0)
);

-- The agreement between Attributes.value_type and the selected Annotations
-- value_* column spans multiple tables. It is validated by the import service
-- rather than by a DuckDB CHECK constraint.

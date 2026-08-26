-- Immutable audit history for mutable Property Annotation changes.

CREATE SEQUENCE property_change_id_seq START WITH 1;

CREATE TABLE PropertyChanges (
    change_id BIGINT PRIMARY KEY DEFAULT nextval('property_change_id_seq'),
    molecule_id BIGINT NOT NULL REFERENCES Molecules(molecule_id),
    entry_id BIGINT NOT NULL REFERENCES Entries(entry_id),
    old_value_number DOUBLE,
    old_value_text VARCHAR,
    old_value_boolean BOOLEAN,
    new_value_number DOUBLE,
    new_value_text VARCHAR,
    new_value_boolean BOOLEAN,
    change_source VARCHAR NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(change_source)) > 0),
    CHECK (
        (CASE WHEN new_value_number IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN new_value_text IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN new_value_boolean IS NOT NULL THEN 1 ELSE 0 END) = 1
    ),
    CHECK (
        (old_value_number IS NULL AND old_value_text IS NULL AND
         old_value_boolean IS NULL) OR
        ((CASE WHEN old_value_number IS NOT NULL THEN 1 ELSE 0 END) +
         (CASE WHEN old_value_text IS NOT NULL THEN 1 ELSE 0 END) +
         (CASE WHEN old_value_boolean IS NOT NULL THEN 1 ELSE 0 END) = 1)
    )
);


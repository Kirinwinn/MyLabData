"""Set-based catalog registration and Annotation insertion operations."""

import json

import duckdb

from mylabdata.contracts.manifest import AnnotationManifest

ATTRIBUTE_DEFINITIONS = "_import_attribute_definitions"
ENTRY_DEFINITIONS = "_import_entry_definitions"
SOURCE_DEFINITIONS = "_import_source_definitions"
INSERT_CANDIDATES = "_annotation_insert_candidates"


def stage_manifest_definitions(
    database_connection: duckdb.DuckDBPyConnection,
    manifest: AnnotationManifest,
) -> None:
    """Stage small Manifest catalogs in connection-local temporary tables."""
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {ATTRIBUTE_DEFINITIONS} (
            attribute_key VARCHAR, attribute_name VARCHAR, value_type VARCHAR,
            unit VARCHAR, description VARCHAR
        )
        """
    )
    database_connection.executemany(
        f"INSERT INTO {ATTRIBUTE_DEFINITIONS} VALUES (?, ?, ?, ?, ?)",
        [
            (
                item.attribute_key,
                item.attribute_name,
                item.value_type,
                item.unit,
                item.description,
            )
            for item in manifest.attributes
        ],
    )
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {SOURCE_DEFINITIONS} AS
        SELECT DISTINCT source_key
        FROM (VALUES {', '.join('( ? )' for _ in manifest.entries)}) AS source(source_key)
        WHERE source_key IS NOT NULL
        """,
        [item.source_key for item in manifest.entries],
    )
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {ENTRY_DEFINITIONS} (
            entry_key VARCHAR, attribute_key VARCHAR, annotation_kind VARCHAR,
            method_name VARCHAR, method_version VARCHAR, conditions_json JSON,
            source_key VARCHAR, is_mutable BOOLEAN, description VARCHAR
        )
        """
    )
    database_connection.executemany(
        f"INSERT INTO {ENTRY_DEFINITIONS} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                item.entry_key,
                item.attribute_key,
                item.annotation_kind,
                item.method_name,
                item.method_version,
                json.dumps(
                    item.conditions,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                item.source_key,
                item.is_mutable,
                item.description,
            )
            for item in manifest.entries
        ],
    )


def register_manifest_catalog(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    processor_name: str,
) -> tuple[int, int, int]:
    """Insert only missing Sources, Attributes, and Entries with SQL sets."""
    sources = _count_new(database_connection, SOURCE_DEFINITIONS, "Sources", "source_key")
    attributes = _count_new(
        database_connection,
        ATTRIBUTE_DEFINITIONS,
        "Attributes",
        "attribute_key",
    )
    entries = _count_new(database_connection, ENTRY_DEFINITIONS, "Entries", "entry_key")

    database_connection.execute(
        f"""
        INSERT INTO Sources (
            source_id, source_key, source_name, source_type, description
        )
        SELECT nextval('source_id_seq'), definition.source_key,
               definition.source_key, 'annotation_package',
               'Created from Annotation Package processor: ' || ?
        FROM {SOURCE_DEFINITIONS} AS definition
        ANTI JOIN Sources AS stored USING (source_key)
        """,
        [processor_name],
    )
    database_connection.execute(
        f"""
        INSERT INTO Attributes (
            attribute_id, attribute_key, attribute_name,
            value_type, unit, description
        )
        SELECT nextval('attribute_id_seq'), definition.attribute_key,
               definition.attribute_name, definition.value_type,
               definition.unit, definition.description
        FROM {ATTRIBUTE_DEFINITIONS} AS definition
        ANTI JOIN Attributes AS stored USING (attribute_key)
        """
    )
    database_connection.execute(
        f"""
        INSERT INTO Entries (
            entry_id, attribute_id, entry_key, annotation_kind,
            method_name, method_version, conditions_json, source_id,
            is_mutable, description
        )
        SELECT nextval('entry_id_seq'), attribute.attribute_id,
               definition.entry_key, definition.annotation_kind,
               definition.method_name, definition.method_version,
               definition.conditions_json, source.source_id,
               definition.is_mutable, definition.description
        FROM {ENTRY_DEFINITIONS} AS definition
        JOIN Attributes AS attribute USING (attribute_key)
        LEFT JOIN Sources AS source USING (source_key)
        ANTI JOIN Entries AS stored USING (entry_key)
        """
    )
    return sources, attributes, entries


def insert_staged_annotations(
    database_connection: duckdb.DuckDBPyConnection,
    staged_table: str,
) -> int:
    """Materialize and insert unique, linkable, not-yet-stored Annotations."""
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {INSERT_CANDIDATES} AS
        SELECT molecule.molecule_id, entry.entry_id,
               candidate.value_number, candidate.value_text,
               candidate.value_boolean
        FROM (
            SELECT * EXCLUDE (duplicate_number)
            FROM (
                SELECT annotation.*,
                       row_number() OVER (
                           PARTITION BY canonical_smiles, entry_key
                           ORDER BY source_row_number
                       ) AS duplicate_number
                FROM {staged_table} AS annotation
            )
            WHERE duplicate_number = 1
        ) AS candidate
        JOIN Molecules AS molecule USING (canonical_smiles)
        JOIN Entries AS entry USING (entry_key)
        ANTI JOIN Annotations AS stored
          ON stored.molecule_id = molecule.molecule_id
         AND stored.entry_id = entry.entry_id
        """
    )
    count = int(
        database_connection.execute(
            f"SELECT count(*) FROM {INSERT_CANDIDATES}"
        ).fetchone()[0]
    )
    database_connection.execute(
        f"""
        INSERT INTO Annotations (
            molecule_id, entry_id, value_number, value_text, value_boolean
        )
        SELECT molecule_id, entry_id, value_number, value_text, value_boolean
        FROM {INSERT_CANDIDATES}
        """
    )
    return count


def create_annotation_import(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    package_name: str,
    package_hash: str,
    processor_name: str,
    total_rows: int,
    duplicate_rows: int,
    existing_rows: int,
    expected_rows: int,
) -> int:
    """Write the completed audit record inside the Annotation transaction."""
    return int(
        database_connection.execute(
            """
            INSERT INTO Imports (
                file_name, file_hash, data_type, status, processor_name,
                total_rows, valid_rows, new_rows, existing_rows,
                duplicate_rows, accepted_rows, failed_rows, finished_at
            ) VALUES (
                ?, ?, 'annotations', 'completed', ?, ?, ?, ?, ?, ?, ?, 0,
                CURRENT_TIMESTAMP
            )
            RETURNING import_id
            """,
            [
                package_name,
                package_hash,
                processor_name,
                total_rows,
                total_rows,
                expected_rows,
                existing_rows,
                duplicate_rows,
                expected_rows,
            ],
        ).fetchone()[0]
    )


def _count_new(
    database_connection: duckdb.DuckDBPyConnection,
    definition_table: str,
    stored_table: str,
    key: str,
) -> int:
    return int(
        database_connection.execute(
            f"""
            SELECT count(*) FROM {definition_table} AS definition
            ANTI JOIN {stored_table} AS stored USING ({key})
            """
        ).fetchone()[0]
    )

"""Read-only DuckDB queries used by Annotation Package preview."""

import json
from pathlib import Path

import duckdb

from mylabdata.contracts.manifest import AnnotationManifest
from mylabdata.core.exceptions import AnnotationPackageError
from mylabdata.schemas.annotations import AttributePreviewItem, EntryPreviewItem

STAGED_ANNOTATIONS = "_preview_annotations"
PREVIEW_ENTRIES = "_preview_entries"

EXPECTED_COLUMNS = {
    "canonical_smiles": "VARCHAR",
    "attribute_key": "VARCHAR",
    "entry_key": "VARCHAR",
    "value_number": "DOUBLE",
    "value_text": "VARCHAR",
    "value_boolean": "BOOLEAN",
}


def validate_and_stage_annotations(
    database_connection: duckdb.DuckDBPyConnection,
    file_path: Path,
) -> None:
    """Validate the fixed Parquet schema and create a connection-local table."""
    try:
        relation = database_connection.read_parquet(str(file_path))
        columns = dict(zip(relation.columns, map(str, relation.types), strict=True))
    except (duckdb.Error, OSError) as exc:
        raise AnnotationPackageError(f"Cannot read annotations.parquet: {exc}") from exc

    if set(columns) != set(EXPECTED_COLUMNS):
        missing = sorted(set(EXPECTED_COLUMNS) - set(columns))
        extra = sorted(set(columns) - set(EXPECTED_COLUMNS))
        raise AnnotationPackageError(
            f"annotations.parquet columns differ; missing={missing}, extra={extra}"
        )
    wrong_types = {
        name: columns[name]
        for name, expected in EXPECTED_COLUMNS.items()
        if columns[name].upper() != expected
    }
    if wrong_types:
        raise AnnotationPackageError(
            f"annotations.parquet column types differ: {wrong_types}"
        )

    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {STAGED_ANNOTATIONS} AS
        SELECT
            row_number() OVER () AS source_row_number,
            trim(canonical_smiles) AS canonical_smiles,
            attribute_key,
            entry_key,
            value_number,
            value_text,
            value_boolean
        FROM read_parquet(?)
        """,
        [str(file_path)],
    )


def compare_catalog(
    database_connection: duckdb.DuckDBPyConnection,
    manifest: AnnotationManifest,
) -> tuple[list[AttributePreviewItem], list[EntryPreviewItem], set[str]]:
    """Classify manifest definitions without writing catalog rows."""
    stored_attributes = {
        row[0]: row[1:]
        for row in database_connection.execute(
            """
            SELECT attribute_key, attribute_name, value_type, unit, description
            FROM Attributes
            """
        ).fetchall()
    }
    attribute_items: list[AttributePreviewItem] = []
    for definition in manifest.attributes:
        stored = stored_attributes.get(definition.attribute_key)
        incoming = (
            definition.attribute_name,
            definition.value_type,
            definition.unit,
            definition.description,
        )
        conflicts = []
        if stored is not None:
            names = ("attribute_name", "value_type", "unit", "description")
            conflicts = [
                name
                for name, left, right in zip(names, stored, incoming)
                if left != right
            ]
        status = "new" if stored is None else ("conflict" if conflicts else "existing")
        attribute_items.append(
            AttributePreviewItem(
                definition=definition,
                status=status,
                conflicts=conflicts,
            )
        )

    stored_entries = {
        row[0]: row[1:]
        for row in database_connection.execute(
            """
            SELECT entry.entry_key, attribute.attribute_key,
                   entry.annotation_kind, entry.method_name,
                   entry.method_version, CAST(entry.conditions_json AS VARCHAR),
                   source.source_key, entry.is_mutable, entry.description
            FROM Entries AS entry
            JOIN Attributes AS attribute USING (attribute_id)
            LEFT JOIN Sources AS source USING (source_id)
            """
        ).fetchall()
    }
    entry_items: list[EntryPreviewItem] = []
    conflicting_entries: set[str] = set()
    for definition in manifest.entries:
        stored = stored_entries.get(definition.entry_key)
        stored_normalized = None
        if stored is not None:
            stored_normalized = (*stored[:4], _canonical_json(stored[4]), *stored[5:])
        incoming = (
            definition.attribute_key,
            definition.annotation_kind,
            definition.method_name,
            definition.method_version,
            _canonical_json(definition.conditions),
            definition.source_key,
            definition.is_mutable,
            definition.description,
        )
        conflicts = []
        if stored_normalized is not None:
            names = (
                "attribute_key",
                "annotation_kind",
                "method_name",
                "method_version",
                "conditions",
                "source_key",
                "is_mutable",
                "description",
            )
            conflicts = [
                name
                for name, left, right in zip(names, stored_normalized, incoming)
                if left != right
            ]
        status = "new" if stored is None else ("conflict" if conflicts else "existing")
        if status == "conflict":
            conflicting_entries.add(definition.entry_key)
        entry_items.append(
            EntryPreviewItem(definition=definition, status=status, conflicts=conflicts)
        )
    return attribute_items, entry_items, conflicting_entries


def annotation_metrics(
    database_connection: duckdb.DuckDBPyConnection,
    manifest: AnnotationManifest,
    blocked_entries: set[str],
) -> dict[str, int]:
    """Calculate validation and preview metrics with set-based SQL."""
    value_types = {
        item.attribute_key: item.value_type for item in manifest.attributes
    }
    database_connection.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {PREVIEW_ENTRIES} (
            entry_key VARCHAR,
            attribute_key VARCHAR,
            value_type VARCHAR,
            blocked BOOLEAN
        )
        """
    )
    database_connection.executemany(
        f"INSERT INTO {PREVIEW_ENTRIES} VALUES (?, ?, ?, ?)",
        [
            (
                item.entry_key,
                item.attribute_key,
                value_types[item.attribute_key],
                item.entry_key in blocked_entries,
            )
            for item in manifest.entries
        ],
    )
    row = database_connection.execute(
        f"""
        WITH checked AS (
            SELECT annotation.*,
                   definition.entry_key IS NOT NULL AS declared_entry,
                   definition.attribute_key AS declared_attribute,
                   definition.value_type,
                   coalesce(definition.blocked, true) AS blocked,
                   ((value_number IS NOT NULL)::INTEGER +
                    (value_text IS NOT NULL)::INTEGER +
                    (value_boolean IS NOT NULL)::INTEGER) AS value_count
            FROM {STAGED_ANNOTATIONS} AS annotation
            LEFT JOIN {PREVIEW_ENTRIES} AS definition USING (entry_key)
        ),
        valid AS (
            SELECT * FROM checked
            WHERE canonical_smiles IS NOT NULL AND length(canonical_smiles) > 0
              AND declared_entry
              AND attribute_key = declared_attribute
              AND value_count = 1
              AND ((value_type = 'number' AND value_number IS NOT NULL) OR
                   (value_type = 'text' AND value_text IS NOT NULL) OR
                   (value_type = 'boolean' AND value_boolean IS NOT NULL))
        ),
        unique_valid AS (
            SELECT * EXCLUDE (duplicate_number)
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY canonical_smiles, entry_key
                    ORDER BY source_row_number
                ) AS duplicate_number
                FROM valid
            )
            WHERE duplicate_number = 1
        ),
        duplicate_groups AS (
            SELECT canonical_smiles, entry_key,
                   count(*) AS row_count,
                   count(DISTINCT struct_pack(
                       number := value_number,
                       text := value_text,
                       boolean_value := value_boolean
                   )) AS value_count
            FROM valid
            GROUP BY canonical_smiles, entry_key
            HAVING count(*) > 1
        )
        SELECT
            (SELECT count(*) FROM checked),
            (SELECT count(*) FROM checked
             WHERE canonical_smiles IS NULL OR length(canonical_smiles) = 0
                OR NOT declared_entry OR attribute_key != declared_attribute
                OR value_count != 1
                OR NOT ((value_type = 'number' AND value_number IS NOT NULL) OR
                        (value_type = 'text' AND value_text IS NOT NULL) OR
                        (value_type = 'boolean' AND value_boolean IS NOT NULL))),
            (SELECT coalesce(sum(row_count - 1), 0) FROM duplicate_groups),
            (SELECT count(*) FROM duplicate_groups WHERE value_count > 1),
            (SELECT count(DISTINCT canonical_smiles) FROM unique_valid
             SEMI JOIN Molecules USING (canonical_smiles)),
            (SELECT count(DISTINCT canonical_smiles) FROM unique_valid
             ANTI JOIN Molecules USING (canonical_smiles)),
            (SELECT count(*) FROM unique_valid AS candidate
             JOIN Molecules AS molecule USING (canonical_smiles)
             JOIN Entries AS entry USING (entry_key)
             SEMI JOIN Annotations AS stored
               ON stored.molecule_id = molecule.molecule_id
              AND stored.entry_id = entry.entry_id),
            (SELECT count(*) FROM unique_valid AS candidate
             JOIN Molecules AS molecule USING (canonical_smiles)
             WHERE NOT blocked
               AND NOT EXISTS (
                   SELECT 1
                   FROM Entries AS entry
                   JOIN Annotations AS stored USING (entry_id)
                   WHERE entry.entry_key = candidate.entry_key
                     AND stored.molecule_id = molecule.molecule_id
               ))
        """
    ).fetchone()
    keys = (
        "annotation_rows",
        "invalid_rows",
        "duplicate_annotations",
        "conflicting_duplicate_groups",
        "linkable_molecules",
        "unlinkable_molecules",
        "existing_annotations",
        "expected_inserts",
    )
    return dict(zip(keys, map(int, row), strict=True))


def _canonical_json(value: object) -> str:
    if isinstance(value, str):
        value = json.loads(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

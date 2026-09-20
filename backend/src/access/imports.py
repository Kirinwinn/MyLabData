"""Third-version DryData access for import audit records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import duckdb

from access.database import DryDataDatabase

if TYPE_CHECKING:
    from access.packages import PackageStore
    from contracts.manifest import AnnotationManifest


@dataclass(frozen=True, slots=True)
class ImportRecord:
    import_id: int
    source_id: int | None
    file_hash: str | None
    data_type: str | None
    status: str | None
    processor: str | None
    total_rows: int | None
    error_message: str | None
    created_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class PackageImportSummary:
    """Database-committed outcome before the package is archived."""

    import_id: int
    package_name: str
    package_hash: str
    total_rows: int
    inserted_rows: int
    existing_rows: int
    duplicate_rows: int
    invalid_rows: int
    created_attributes: int = 0
    created_entries: int = 0
    created_sources: int = 0


class ImportRepository:
    """Persist import audit rows using the actual third-version column names."""

    def __init__(self, database: DryDataDatabase) -> None:
        self.database = database

    def list(self, *, limit: int = 100, offset: int = 0) -> list[ImportRecord]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT import_id, source_id, file_hash, data_type, status, processor,
                       total_rows, error_message, created_at, finished_at
                FROM Imports
                ORDER BY import_id DESC
                LIMIT ? OFFSET ?
                """,
                [limit, offset],
            ).fetchall()
        return [_record_from_row(row) for row in rows]

    def get(self, import_id: int) -> ImportRecord | None:
        """Read one v3 import audit record by its stable identifier."""
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT import_id, source_id, file_hash, data_type, status, processor,
                       total_rows, error_message, created_at, finished_at
                FROM Imports WHERE import_id = ?
                """,
                [import_id],
            ).fetchone()
        return _record_from_row(row) if row else None

    def create(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        source_id: int | None,
        file_hash: str,
        data_type: str,
        processor: str,
        total_rows: int,
    ) -> int:
        """Create one processing audit row inside an existing write transaction."""
        import_id = int(
            connection.execute("SELECT COALESCE(MAX(import_id), 0) + 1 FROM Imports").fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO Imports (
                import_id, source_id, file_hash, data_type, status, processor,
                total_rows, error_message, created_at, finished_at
            ) VALUES (?, ?, ?, ?, 'processing', ?, ?, NULL, CURRENT_TIMESTAMP, NULL)
            """,
            [import_id, source_id, file_hash, data_type, processor, total_rows],
        )
        return import_id

    def finish(
        self,
        connection: duckdb.DuckDBPyConnection,
        import_id: int,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Mark an existing import as completed or failed within a transaction."""
        connection.execute(
            """
            UPDATE Imports
            SET status = ?, error_message = ?, finished_at = CURRENT_TIMESTAMP
            WHERE import_id = ?
            """,
            [status, error_message, import_id],
        )

    def import_molecule_package(
        self,
        connection: duckdb.DuckDBPyConnection,
        packages: PackageStore,
        package_id: str,
    ) -> PackageImportSummary:
        """Import one managed Molecules Parquet file inside the caller transaction."""
        descriptor = packages.descriptor(package_id)
        if descriptor.kind != "molecules":
            raise ValueError("Expected a Molecules package")
        package_hash = packages.fingerprint(package_id)
        path = packages._incoming_path(descriptor)
        relation = connection.read_parquet(str(path))
        if "canonical_smiles" not in relation.columns:
            raise ValueError("Molecules Parquet requires canonical_smiles")
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_molecule_stage AS
            SELECT row_number() OVER () AS source_row, trim(canonical_smiles) AS canonical_smiles
            FROM read_parquet(?)
            """,
            [str(path)],
        )
        total_rows, valid_rows, distinct_rows, existing_rows = map(
            int,
            connection.execute(
                """
                WITH valid AS (
                    SELECT canonical_smiles FROM _mld_molecule_stage
                    WHERE canonical_smiles IS NOT NULL AND length(canonical_smiles) > 0
                ), distinct_valid AS (SELECT DISTINCT canonical_smiles FROM valid)
                SELECT
                    (SELECT count(*) FROM _mld_molecule_stage),
                    (SELECT count(*) FROM valid),
                    (SELECT count(*) FROM distinct_valid),
                    (SELECT count(*) FROM distinct_valid AS candidate
                     SEMI JOIN Molecules AS molecule USING (canonical_smiles))
                """
            ).fetchone(),
        )
        import_id = self.create(
            connection,
            source_id=None,
            file_hash=package_hash,
            data_type="molecules",
            processor="mylabdata.v3.molecule_import",
            total_rows=total_rows,
        )
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_new_molecules AS
            SELECT canonical_smiles, min(source_row) AS source_row
            FROM _mld_molecule_stage AS candidate
            ANTI JOIN Molecules AS stored USING (canonical_smiles)
            WHERE canonical_smiles IS NOT NULL AND length(canonical_smiles) > 0
            GROUP BY canonical_smiles
            """
        )
        inserted_rows = int(
            connection.execute("SELECT count(*) FROM _mld_new_molecules").fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO Molecules (
                molecule_id, lab_id, canonical_smiles, channel, created_at
            )
            SELECT
                (SELECT coalesce(max(molecule_id), 0) FROM Molecules)
                    + row_number() OVER (ORDER BY source_row),
                'L' || lpad(
                    CAST(
                        (SELECT coalesce(max(molecule_id), 0) FROM Molecules)
                            + row_number() OVER (ORDER BY source_row) AS VARCHAR
                    ),
                    8,
                    '0'
                ),
                canonical_smiles,
                NULL,
                CURRENT_TIMESTAMP
            FROM _mld_new_molecules
            """
        )
        self.finish(connection, import_id, status="completed")
        return PackageImportSummary(
            import_id=import_id,
            package_name=descriptor.name,
            package_hash=package_hash,
            total_rows=total_rows,
            inserted_rows=inserted_rows,
            existing_rows=existing_rows,
            duplicate_rows=valid_rows - distinct_rows,
            invalid_rows=total_rows - valid_rows,
        )

    def import_annotation_package(
        self,
        connection: duckdb.DuckDBPyConnection,
        packages: PackageStore,
        package_id: str,
        manifest: AnnotationManifest,
    ) -> PackageImportSummary:
        """Register a compatible manifest and import its linkable Annotation rows."""
        descriptor = packages.descriptor(package_id)
        if descriptor.kind != "annotations":
            raise ValueError("Expected an Annotation package")
        package_hash = packages.fingerprint(package_id)
        package_path = packages._incoming_path(descriptor)
        annotation_path = package_path / "annotations.parquet"
        if not annotation_path.is_file():
            raise ValueError("Annotation package is missing annotations.parquet")
        relation = connection.read_parquet(str(annotation_path))
        expected_columns = {
            "canonical_smiles",
            "attribute_key",
            "entry_key",
            "value_number",
            "value_text",
            "value_boolean",
        }
        if set(relation.columns) != expected_columns:
            raise ValueError("annotations.parquet has an unsupported column set")
        created_sources, created_attributes, created_entries = self._register_manifest(
            connection, manifest
        )
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_annotation_stage AS
            SELECT row_number() OVER () AS source_row, trim(canonical_smiles) AS canonical_smiles,
                   attribute_key, entry_key, value_number, value_text, value_boolean
            FROM read_parquet(?)
            """,
            [str(annotation_path)],
        )
        total_rows = int(
            connection.execute("SELECT count(*) FROM _mld_annotation_stage").fetchone()[0]
        )
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_valid_annotations AS
            SELECT molecule.molecule_id, entry.entry_id, stage.value_number,
                   stage.value_text, stage.value_boolean, stage.source_row
            FROM _mld_annotation_stage AS stage
            JOIN Entries AS entry USING (entry_key)
            JOIN Attributes AS attribute USING (attribute_id)
            JOIN Molecules AS molecule USING (canonical_smiles)
            WHERE stage.attribute_key = attribute.attribute_key
              AND ((stage.value_number IS NOT NULL)::INTEGER +
                   (stage.value_text IS NOT NULL)::INTEGER +
                   (stage.value_boolean IS NOT NULL)::INTEGER) = 1
              AND ((attribute.value_type = 'number' AND stage.value_number IS NOT NULL) OR
                   (attribute.value_type = 'text' AND stage.value_text IS NOT NULL) OR
                   (attribute.value_type = 'boolean' AND stage.value_boolean IS NOT NULL))
            """
        )
        valid_rows = int(
            connection.execute("SELECT count(*) FROM _mld_valid_annotations").fetchone()[0]
        )
        duplicate_rows = valid_rows - int(
            connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT molecule_id, entry_id FROM _mld_valid_annotations
                    GROUP BY molecule_id, entry_id
                )
                """
            ).fetchone()[0]
        )
        existing_rows = int(
            connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT * EXCLUDE (row_number) FROM (
                        SELECT *, row_number() OVER (
                            PARTITION BY molecule_id, entry_id ORDER BY source_row
                        ) AS row_number
                        FROM _mld_valid_annotations
                    ) WHERE row_number = 1
                ) AS candidate
                SEMI JOIN Annotations AS stored
                  ON stored.molecule_id = candidate.molecule_id
                 AND stored.entry_id = candidate.entry_id
                """
            ).fetchone()[0]
        )
        import_id = self.create(
            connection,
            source_id=None,
            file_hash=package_hash,
            data_type="annotations",
            processor=manifest.processor_name,
            total_rows=total_rows,
        )
        connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE _mld_new_annotations AS
            SELECT candidate.*
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY molecule_id, entry_id ORDER BY source_row
                ) AS row_number
                FROM _mld_valid_annotations
            ) AS candidate
            ANTI JOIN Annotations AS stored
              ON stored.molecule_id = candidate.molecule_id
             AND stored.entry_id = candidate.entry_id
            WHERE candidate.row_number = 1
            """
        )
        inserted_rows = int(
            connection.execute("SELECT count(*) FROM _mld_new_annotations").fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO Annotations (
                molecule_id, entry_id, value_number, value_text, value_boolean,
                created_at, updated_at
            )
            SELECT molecule_id, entry_id, value_number, value_text, value_boolean,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM _mld_new_annotations
            """
        )
        self.finish(connection, import_id, status="completed")
        return PackageImportSummary(
            import_id=import_id,
            package_name=descriptor.name,
            package_hash=package_hash,
            total_rows=total_rows,
            inserted_rows=inserted_rows,
            existing_rows=existing_rows,
            duplicate_rows=duplicate_rows,
            invalid_rows=total_rows - valid_rows,
            created_attributes=created_attributes,
            created_entries=created_entries,
            created_sources=created_sources,
        )

    @staticmethod
    def _register_manifest(
        connection: duckdb.DuckDBPyConnection,
        manifest: AnnotationManifest,
    ) -> tuple[int, int, int]:
        source_keys = sorted({entry.source_key for entry in manifest.entries if entry.source_key})
        created_sources = 0
        for source_key in source_keys:
            if (
                connection.execute(
                    "SELECT 1 FROM Sources WHERE source_key = ?", [source_key]
                ).fetchone()
                is None
            ):
                source_id = int(
                    connection.execute(
                        "SELECT coalesce(max(source_id), 0) + 1 FROM Sources"
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO Sources (source_id, source_key, source_type, description)
                    VALUES (?, ?, 'annotation_package', ?)
                    """,
                    [source_id, source_key, f"Created by {manifest.processor_name}"],
                )
                created_sources += 1
        created_attributes = 0
        for definition in manifest.attributes:
            existing = connection.execute(
                """
                SELECT attribute_name, value_type, unit, description
                FROM Attributes WHERE attribute_key = ?
                """,
                [definition.attribute_key],
            ).fetchone()
            incoming = (
                definition.attribute_name,
                definition.value_type,
                definition.unit,
                definition.description,
            )
            if existing is not None and tuple(existing) != incoming:
                raise ValueError(f"Conflicting Attribute definition: {definition.attribute_key}")
            if existing is None:
                attribute_id = int(
                    connection.execute(
                        "SELECT coalesce(max(attribute_id), 0) + 1 FROM Attributes"
                    ).fetchone()[0]
                )
                connection.execute(
                    """
                    INSERT INTO Attributes (
                        attribute_id, attribute_key, attribute_name, value_type, unit, description
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [attribute_id, definition.attribute_key, *incoming],
                )
                created_attributes += 1
        created_entries = 0
        for definition in manifest.entries:
            if (
                connection.execute(
                    "SELECT 1 FROM Entries WHERE entry_key = ?", [definition.entry_key]
                ).fetchone()
                is not None
            ):
                continue
            entry_id = int(
                connection.execute("SELECT coalesce(max(entry_id), 0) + 1 FROM Entries").fetchone()[
                    0
                ]
            )
            attribute_id = int(
                connection.execute(
                    "SELECT attribute_id FROM Attributes WHERE attribute_key = ?",
                    [definition.attribute_key],
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO Entries (
                    entry_id, attribute_id, entry_key, annotation_kind, method_name,
                    method_version, conditions_json, is_mutable, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    entry_id,
                    attribute_id,
                    definition.entry_key,
                    definition.annotation_kind,
                    definition.method_name,
                    definition.method_version,
                    json.dumps(definition.conditions, ensure_ascii=False, sort_keys=True),
                    definition.is_mutable,
                    definition.description,
                ],
            )
            created_entries += 1
        return created_sources, created_attributes, created_entries


def _record_from_row(row: tuple) -> ImportRecord:
    return ImportRecord(
        import_id=int(row[0]),
        source_id=int(row[1]) if row[1] is not None else None,
        file_hash=str(row[2]) if row[2] is not None else None,
        data_type=str(row[3]) if row[3] is not None else None,
        status=str(row[4]) if row[4] is not None else None,
        processor=str(row[5]) if row[5] is not None else None,
        total_rows=int(row[6]) if row[6] is not None else None,
        error_message=str(row[7]) if row[7] is not None else None,
        created_at=row[8],
        finished_at=row[9],
    )

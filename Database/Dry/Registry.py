"""MLD2 DuckDB registry for DryData.

Prepared molecule files are imported directly with DuckDB so large CSV and
Parquet inputs do not need to be loaded into Python memory. Attribute values
remain in their processed files; the registry records identity, provenance,
imports, and reusable query caches.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import duckdb


DEFAULT_EXPERIDATA_ROOT = Path(
    os.getenv("EXPERIDATA_ROOT", str(Path.home() / "Documents" / "ExperiData"))
)
DEFAULT_DRY_ROOT = DEFAULT_EXPERIDATA_ROOT / "DryData"
DEFAULT_REGISTRY_PATH = DEFAULT_DRY_ROOT / "Registry" / "DryData.duckdb"
DEFAULT_SCHEMA_PATH = Path(__file__).with_name("schema_v1.sql")

WORKFLOW_STAGES = ("Incoming", "Processed", "Failed")
DATA_CATEGORIES = ("Molecules", "Traits", "Predictions", "Annotations")
SOURCE_TYPES = {"external", "generated", "derived", "manual", "system"}
SOURCE_CLASSES = {"external", "generated", "derived", "manual"}
ATTRIBUTE_CATEGORIES = {"trait", "prediction", "annotation"}
VALUE_TYPES = {"float", "integer", "boolean", "string", "json"}


class RegistryError(RuntimeError):
    """Raised when registry input or state is invalid."""


def _json_value(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_json_fields(row: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    for field in fields:
        value = row.get(field)
        if isinstance(value, str):
            try:
                row[field] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return row


def _rows_as_dicts(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class DryRegistry:
    """Operational interface to the MLD2 DryData DuckDB registry."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_REGISTRY_PATH,
        dry_root: str | Path = DEFAULT_DRY_ROOT,
        schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    ) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.dry_root = Path(dry_root).expanduser().resolve()
        self.schema_path = Path(schema_path).expanduser().resolve()

    def initialize(self) -> Path:
        """Create the workflow directories and idempotently apply schema v1."""
        for stage in WORKFLOW_STAGES:
            for category in DATA_CATEGORIES:
                (self.dry_root / stage / category).mkdir(parents=True, exist_ok=True)
        (self.dry_root / "Cache").mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.schema_path.is_file():
            raise RegistryError(f"Schema file not found: {self.schema_path}")

        connection = duckdb.connect(str(self.db_path))
        try:
            connection.execute(self.schema_path.read_text(encoding="utf-8"))
        finally:
            connection.close()
        return self.db_path

    def connect(self, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        if not self.db_path.exists():
            if read_only:
                raise RegistryError(f"Registry does not exist: {self.db_path}")
            self.initialize()
        return duckdb.connect(str(self.db_path), read_only=read_only)

    def register_source(
        self,
        source_key: str,
        source_name: str,
        source_type: str,
        *,
        source_uri: str | None = None,
        description: str | None = None,
        metadata: Any = None,
    ) -> int:
        source_key = source_key.strip()
        source_name = source_name.strip()
        source_type = source_type.lower().strip()
        if not source_key or not source_name:
            raise RegistryError("source_key and source_name must not be empty")
        if source_type not in SOURCE_TYPES:
            raise RegistryError(f"Unsupported source_type: {source_type}")

        connection = self.connect()
        try:
            existing = connection.execute(
                "SELECT source_id, source_type FROM Sources WHERE source_key = ?",
                [source_key],
            ).fetchone()
            if existing is not None:
                if existing[1] != source_type:
                    raise RegistryError(
                        f"Source {source_key!r} is already registered as {existing[1]!r}"
                    )
                return int(existing[0])
            row = connection.execute(
                """
                INSERT INTO Sources (
                    source_key, source_name, source_type, source_uri,
                    description, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
                RETURNING source_id
                """,
                [
                    source_key, source_name, source_type, source_uri,
                    description, _json_value(metadata),
                ],
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def register_attribute(
        self,
        attribute_key: str,
        attribute_name: str,
        attribute_category: str,
        value_type: str,
        *,
        unit: str | None = None,
        description: str | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
        source_id: int | None = None,
        metadata: Any = None,
    ) -> int:
        attribute_key = attribute_key.strip()
        attribute_name = attribute_name.strip()
        attribute_category = attribute_category.lower().strip()
        value_type = value_type.lower().strip()
        if not attribute_key or not attribute_name:
            raise RegistryError("attribute_key and attribute_name must not be empty")
        if attribute_category not in ATTRIBUTE_CATEGORIES:
            raise RegistryError(f"Unsupported attribute_category: {attribute_category}")
        if value_type not in VALUE_TYPES:
            raise RegistryError(f"Unsupported value_type: {value_type}")

        connection = self.connect()
        try:
            return self._register_attribute_with_connection(
                connection,
                attribute_key,
                attribute_name,
                attribute_category,
                value_type,
                unit=unit,
                description=description,
                model_name=model_name,
                model_version=model_version,
                source_id=source_id,
                metadata=metadata,
            )
        finally:
            connection.close()

    @staticmethod
    def _register_attribute_with_connection(
        connection: duckdb.DuckDBPyConnection,
        attribute_key: str,
        attribute_name: str,
        attribute_category: str,
        value_type: str,
        *,
        unit: str | None = None,
        description: str | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
        source_id: int | None = None,
        metadata: Any = None,
    ) -> int:
        existing = connection.execute(
            """
            SELECT attribute_id, attribute_category, value_type, source_id
            FROM Attributes WHERE attribute_key = ?
            """,
            [attribute_key],
        ).fetchone()
        if existing is not None:
            if existing[1] != attribute_category or existing[2] != value_type:
                raise RegistryError(
                    f"Attribute {attribute_key!r} has a conflicting category or type"
                )
            if source_id is not None and existing[3] not in (None, source_id):
                raise RegistryError(
                    f"Attribute {attribute_key!r} belongs to another source"
                )
            return int(existing[0])
        row = connection.execute(
            """
            INSERT INTO Attributes (
                attribute_key, attribute_name, attribute_category, value_type,
                unit, description, model_name, model_version, source_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING attribute_id
            """,
            [
                attribute_key, attribute_name, attribute_category, value_type,
                unit, description, model_name, model_version, source_id,
                _json_value(metadata),
            ],
        ).fetchone()
        return int(row[0])

    def import_molecules(
        self,
        file_path: str | Path,
        *,
        source_key: str,
        source_name: str,
        source_type: str,
        source_class: str | None = None,
        calculate_checksum: bool = True,
    ) -> dict[str, Any]:
        """Import and deduplicate prepared molecules from CSV or Parquet.

        Accepted identity columns are `canonical_smiles`, `SMILES`, or `smiles`.
        Optional columns are `inchikey` and `original_smiles`. Existing
        molecules are matched by canonical SMILES or InChIKey and are not reinserted.
        """
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise RegistryError(f"Input file not found: {path}")

        file_format, reader_sql = self._reader_sql(path, all_varchar=True)
        source_type = source_type.lower().strip()
        source_class = (source_class or source_type).lower().strip()
        if source_class not in SOURCE_CLASSES:
            raise RegistryError(f"Unsupported source_class: {source_class}")

        source_id = self.register_source(
            source_key, source_name, source_type, source_uri=str(path.parent)
        )
        connection = self.connect()
        import_id: int | None = None

        try:
            import_id = int(connection.execute(
                """
                INSERT INTO Imports (
                    source_id, data_category, source_class, original_filename,
                    input_path, file_format, checksum_sha256, status, processor_name,
                    processor_version, started_at
                ) VALUES (?, 'molecules', ?, ?, ?, ?, ?, 'processing',
                          'MyLabData.DryRegistry', '1', now())
                RETURNING import_id
                """,
                [
                    source_id, source_class, path.name, str(path), file_format,
                    None,
                ],
            ).fetchone()[0])

            checksum = _sha256(path) if calculate_checksum else None

            columns = self._reader_columns(connection, reader_sql)
            canonical_column = self._find_column(
                columns, ("canonical_smiles", "SMILES", "smiles")
            )
            if canonical_column is None:
                raise RegistryError(
                    "Molecule input requires canonical_smiles or SMILES column"
                )
            inchikey_column = self._find_column(columns, ("inchikey", "InChIKey"))
            original_column = self._find_column(
                columns, ("original_smiles", "Original_SMILES")
            )

            canonical_expr = (
                f"trim(cast({_quote_identifier(canonical_column)} AS VARCHAR))"
            )
            inchikey_expr = (
                f"nullif(trim(cast({_quote_identifier(inchikey_column)} AS VARCHAR)), '')"
                if inchikey_column else "NULL::VARCHAR"
            )
            original_expr = (
                f"nullif(trim(cast({_quote_identifier(original_column)} AS VARCHAR)), '')"
                if original_column else canonical_expr
            )

            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                f"""
                CREATE TEMP TABLE _incoming_raw AS
                SELECT
                    {canonical_expr} AS canonical_smiles,
                    {inchikey_expr} AS inchikey,
                    {original_expr} AS original_smiles
                FROM {reader_sql}
                """
            )
            total_rows = int(connection.execute(
                "SELECT count(*) FROM _incoming_raw"
            ).fetchone()[0])
            valid_rows = int(connection.execute(
                """
                SELECT count(*) FROM _incoming_raw
                WHERE canonical_smiles IS NOT NULL AND canonical_smiles <> ''
                """
            ).fetchone()[0])

            identity_conflicts = int(connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT canonical_smiles
                    FROM _incoming_raw
                    WHERE canonical_smiles IS NOT NULL AND canonical_smiles <> ''
                      AND inchikey IS NOT NULL
                    GROUP BY canonical_smiles
                    HAVING count(DISTINCT inchikey) > 1
                    UNION ALL
                    SELECT inchikey
                    FROM _incoming_raw
                    WHERE canonical_smiles IS NOT NULL AND canonical_smiles <> ''
                      AND inchikey IS NOT NULL
                    GROUP BY inchikey
                    HAVING count(DISTINCT canonical_smiles) > 1
                ) conflicts
                """
            ).fetchone()[0])
            if identity_conflicts:
                raise RegistryError(
                    "Molecule input contains conflicting canonical SMILES/InChIKey mappings"
                )

            connection.execute(
                """
                CREATE TEMP TABLE _incoming_molecules AS
                SELECT canonical_smiles, inchikey, original_smiles
                FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY canonical_smiles
                        ORDER BY inchikey NULLS LAST
                    ) AS smiles_rank
                    FROM _incoming_raw
                    WHERE canonical_smiles IS NOT NULL AND canonical_smiles <> ''
                )
                WHERE smiles_rank = 1
                QUALIFY row_number() OVER (
                    PARTITION BY CASE
                        WHEN inchikey IS NULL THEN 'SMILES:' || canonical_smiles
                        ELSE 'INCHIKEY:' || inchikey
                    END
                    ORDER BY canonical_smiles
                ) = 1
                """
            )
            inserted_rows = int(connection.execute(
                """
                SELECT count(*)
                FROM _incoming_molecules incoming
                WHERE NOT EXISTS (
                    SELECT 1 FROM Molecules existing
                    WHERE existing.canonical_smiles = incoming.canonical_smiles
                       OR (incoming.inchikey IS NOT NULL
                           AND existing.inchikey = incoming.inchikey)
                )
                """
            ).fetchone()[0])

            connection.execute(
                """
                WITH candidates AS (
                    SELECT incoming.*
                    FROM _incoming_molecules incoming
                    WHERE NOT EXISTS (
                        SELECT 1 FROM Molecules existing
                        WHERE existing.canonical_smiles = incoming.canonical_smiles
                           OR (incoming.inchikey IS NOT NULL
                               AND existing.inchikey = incoming.inchikey)
                    )
                ), numbered AS (
                    SELECT nextval('molecule_id_seq') AS molecule_id, *
                    FROM candidates
                )
                INSERT INTO Molecules (
                    molecule_id, lab_id, canonical_smiles, inchikey,
                    original_smiles, primary_source_id
                )
                SELECT
                    molecule_id,
                    'L' || lpad(cast(molecule_id AS VARCHAR), 8, '0'),
                    canonical_smiles, inchikey, original_smiles, ?
                FROM numbered
                """,
                [source_id],
            )
            rejected_rows = total_rows - valid_rows
            duplicate_rows = valid_rows - inserted_rows
            connection.execute(
                """
                UPDATE Imports SET
                    status = 'completed', total_rows = ?, accepted_rows = ?,
                    rejected_rows = ?, duplicate_rows = ?, processed_path = ?,
                    checksum_sha256 = ?, completed_at = now()
                WHERE import_id = ?
                """,
                [
                    total_rows, inserted_rows, rejected_rows, duplicate_rows,
                    str(path), checksum, import_id,
                ],
            )
            connection.execute("COMMIT")
            return {
                "import_id": import_id,
                "status": "completed",
                "input_path": str(path),
                "total_rows": total_rows,
                "accepted_rows": inserted_rows,
                "rejected_rows": rejected_rows,
                "duplicate_rows": duplicate_rows,
            }
        except Exception as exc:
            try:
                connection.execute("ROLLBACK")
            except duckdb.TransactionException:
                pass
            if import_id is not None:
                connection.execute(
                    """
                    UPDATE Imports SET status = 'failed', error_message = ?,
                        completed_at = now()
                    WHERE import_id = ?
                    """,
                    [str(exc), import_id],
                )
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError(f"Molecule import failed: {exc}") from exc
        finally:
            connection.close()

    def register_attribute_file(
        self,
        file_path: str | Path,
        *,
        source_key: str,
        source_name: str,
        source_type: str,
        attribute_category: str,
        attribute_prefix: str,
        source_class: str | None = None,
        model_name: str | None = None,
        exclude_columns: Iterable[str] = (),
        calculate_checksum: bool = True,
        validate_identities: bool = True,
    ) -> dict[str, Any]:
        """Register a processed trait, prediction, or annotation data file.

        Values stay in the CSV or Parquet file. Every non-identity column is
        added to the Attributes catalog, while Imports records the file path,
        checksum, row count, and attribute keys for later DuckDB queries.
        """
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise RegistryError(f"Input file not found: {path}")
        attribute_category = attribute_category.lower().strip()
        if attribute_category not in ATTRIBUTE_CATEGORIES:
            raise RegistryError(f"Unsupported attribute_category: {attribute_category}")
        attribute_prefix = attribute_prefix.strip().strip(".")
        if not attribute_prefix:
            raise RegistryError("attribute_prefix must not be empty")

        file_format, reader_sql = self._reader_sql(path, all_varchar=False)
        source_type = source_type.lower().strip()
        source_class = (source_class or source_type).lower().strip()
        if source_class not in SOURCE_CLASSES:
            raise RegistryError(f"Unsupported source_class: {source_class}")
        source_id = self.register_source(
            source_key, source_name, source_type, source_uri=str(path.parent)
        )
        excluded = {
            "smiles", "canonical_smiles", "original_smiles", "inchikey", "lab_id",
            *(column.lower() for column in exclude_columns),
        }
        data_category = {
            "trait": "traits",
            "prediction": "predictions",
            "annotation": "annotations",
        }[attribute_category]
        connection = self.connect()
        import_id: int | None = None
        try:
            import_id = int(connection.execute(
                """
                INSERT INTO Imports (
                    source_id, data_category, source_class, original_filename,
                    input_path, file_format, status, processor_name,
                    processor_version, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'processing',
                          'MyLabData.DryRegistry', '1', now())
                RETURNING import_id
                """,
                [
                    source_id, data_category, source_class, path.name,
                    str(path), file_format,
                ],
            ).fetchone()[0])

            checksum = _sha256(path) if calculate_checksum else None
            cursor = connection.execute(f"SELECT * FROM {reader_sql} LIMIT 0")
            columns = [item[0] for item in cursor.description]
            column_types = {
                item[0]: str(item[1])
                for item in cursor.description
                if item[0].lower() not in excluded
            }
            identity_column = self._find_column(
                columns, ("canonical_smiles", "SMILES", "smiles", "lab_id", "inchikey")
            )
            if identity_column is None:
                raise RegistryError(
                    "Attribute input requires SMILES, canonical_smiles, lab_id, or inchikey"
                )
            if not column_types:
                raise RegistryError("Attribute input does not contain attribute columns")

            identity_lookup = {
                "canonical_smiles": "canonical_smiles",
                "smiles": "canonical_smiles",
                "lab_id": "lab_id",
                "inchikey": "inchikey",
            }[identity_column.lower()]
            identity_expr = (
                f"trim(cast(input.{_quote_identifier(identity_column)} AS VARCHAR))"
            )
            total_rows = int(connection.execute(
                f"SELECT count(*) FROM {reader_sql}"
            ).fetchone()[0])
            if validate_identities:
                accepted_rows = int(connection.execute(
                    f"""
                    SELECT count(*) FROM {reader_sql} input
                    WHERE {identity_expr} <> ''
                      AND EXISTS (
                          SELECT 1 FROM Molecules molecule
                          WHERE cast(molecule.{_quote_identifier(identity_lookup)} AS VARCHAR)
                                = {identity_expr}
                      )
                    """
                ).fetchone()[0])
            else:
                accepted_rows = int(connection.execute(
                    f"SELECT count(*) FROM {reader_sql} input WHERE {identity_expr} <> ''"
                ).fetchone()[0])
            rejected_rows = total_rows - accepted_rows
            if total_rows > 0 and accepted_rows == 0:
                raise RegistryError(
                    "No attribute rows match molecules already registered in Molecules"
                )

            connection.execute("BEGIN TRANSACTION")
            attribute_keys = []
            for column_name, duckdb_type in column_types.items():
                attribute_key = f"{attribute_category}.{attribute_prefix}.{column_name}"
                self._register_attribute_with_connection(
                    connection,
                    attribute_key,
                    column_name,
                    attribute_category,
                    self._value_type(duckdb_type),
                    model_name=model_name,
                    source_id=source_id,
                    metadata={
                        "source_column": column_name,
                        "source_file": str(path),
                        "duckdb_type": duckdb_type,
                    },
                )
                attribute_keys.append(attribute_key)

            connection.execute(
                """
                UPDATE Imports SET
                    status = 'completed', processed_path = ?, checksum_sha256 = ?,
                    total_rows = ?, accepted_rows = ?, rejected_rows = ?,
                    duplicate_rows = 0, attribute_keys = ?, completed_at = now()
                WHERE import_id = ?
                """,
                [
                    str(path), checksum, total_rows, accepted_rows, rejected_rows,
                    _json_value(attribute_keys), import_id,
                ],
            )
            connection.execute("COMMIT")
            return {
                "import_id": import_id,
                "status": "completed",
                "input_path": str(path),
                "total_rows": total_rows,
                "accepted_rows": accepted_rows,
                "rejected_rows": rejected_rows,
                "attribute_keys": attribute_keys,
            }
        except Exception as exc:
            try:
                connection.execute("ROLLBACK")
            except duckdb.TransactionException:
                pass
            if import_id is not None:
                connection.execute(
                    """
                    UPDATE Imports SET status = 'failed', error_message = ?,
                        completed_at = now()
                    WHERE import_id = ?
                    """,
                    [str(exc), import_id],
                )
            if isinstance(exc, RegistryError):
                raise
            raise RegistryError(f"Attribute file registration failed: {exc}") from exc
        finally:
            connection.close()

    def status(self) -> dict[str, Any]:
        connection = self.connect(read_only=True)
        try:
            counts = {
                table: int(connection.execute(
                    f"SELECT count(*) FROM {_quote_identifier(table)}"
                ).fetchone()[0])
                for table in (
                    "Molecules", "Attributes", "Sources", "Imports",
                    "AttributeDistributions", "AttributeStats",
                )
            }
            return {"database": str(self.db_path), "counts": counts}
        finally:
            connection.close()

    def search_molecules(
        self, query: str | None = None, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        connection = self.connect(read_only=True)
        try:
            if query:
                cursor = connection.execute(
                    """
                    SELECT molecule_id, lab_id, canonical_smiles, inchikey,
                           original_smiles, primary_source_id, created_at, updated_at
                    FROM Molecules
                    WHERE lab_id ILIKE ? OR canonical_smiles ILIKE ? OR inchikey ILIKE ?
                    ORDER BY molecule_id LIMIT ? OFFSET ?
                    """,
                    [query, f"%{query}%", f"%{query}%", limit, offset],
                )
            else:
                cursor = connection.execute(
                    """
                    SELECT molecule_id, lab_id, canonical_smiles, inchikey,
                           original_smiles, primary_source_id, created_at, updated_at
                    FROM Molecules ORDER BY molecule_id LIMIT ? OFFSET ?
                    """,
                    [limit, offset],
                )
            return _rows_as_dicts(cursor)
        finally:
            connection.close()

    def list_imports(self, *, limit: int = 100) -> list[dict[str, Any]]:
        connection = self.connect(read_only=True)
        try:
            rows = _rows_as_dicts(connection.execute(
                "SELECT * FROM Imports ORDER BY import_id DESC LIMIT ?",
                [max(1, min(int(limit), 1000))],
            ))
            return [
                _decode_json_fields(row, ("attribute_keys", "metadata"))
                for row in rows
            ]
        finally:
            connection.close()

    def cache_distribution(
        self,
        attribute_key: str,
        scope_hash: str,
        data_revision: str,
        *,
        distribution_type: str,
        non_null_count: int,
        null_count: int,
        scope_definition: Any = None,
        bin_edges: Any = None,
        bin_counts: Any = None,
        category_counts: Any = None,
    ) -> int:
        if distribution_type not in {"histogram", "categories"}:
            raise RegistryError(f"Unsupported distribution_type: {distribution_type}")
        connection = self.connect()
        try:
            attribute_id = self._attribute_id(connection, attribute_key)
            row = connection.execute(
                """
                INSERT INTO AttributeDistributions (
                    attribute_id, scope_hash, scope_definition, data_revision,
                    distribution_type, bin_edges, bin_counts, category_counts,
                    non_null_count, null_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (attribute_id, scope_hash, data_revision) DO UPDATE SET
                    scope_definition = excluded.scope_definition,
                    distribution_type = excluded.distribution_type,
                    bin_edges = excluded.bin_edges,
                    bin_counts = excluded.bin_counts,
                    category_counts = excluded.category_counts,
                    non_null_count = excluded.non_null_count,
                    null_count = excluded.null_count,
                    computed_at = now()
                RETURNING distribution_id
                """,
                [
                    attribute_id, scope_hash, _json_value(scope_definition),
                    data_revision, distribution_type, _json_value(bin_edges),
                    _json_value(bin_counts), _json_value(category_counts),
                    non_null_count, null_count,
                ],
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def get_distribution(
        self, attribute_key: str, scope_hash: str, data_revision: str
    ) -> dict[str, Any] | None:
        connection = self.connect(read_only=True)
        try:
            cursor = connection.execute(
                """
                SELECT distribution.*
                FROM AttributeDistributions distribution
                JOIN Attributes attribute USING (attribute_id)
                WHERE attribute.attribute_key = ? AND scope_hash = ?
                  AND data_revision = ?
                  AND (expires_at IS NULL OR expires_at > now())
                """,
                [attribute_key, scope_hash, data_revision],
            )
            rows = _rows_as_dicts(cursor)
            if not rows:
                return None
            return _decode_json_fields(
                rows[0],
                ("scope_definition", "bin_edges", "bin_counts", "category_counts"),
            )
        finally:
            connection.close()

    def cache_stats(
        self,
        attribute_key: str,
        scope_hash: str,
        data_revision: str,
        *,
        row_count: int,
        non_null_count: int,
        null_count: int,
        distinct_count: int | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        mean_value: float | None = None,
        stddev_value: float | None = None,
        median_value: float | None = None,
        q1_value: float | None = None,
        q3_value: float | None = None,
        min_text: str | None = None,
        max_text: str | None = None,
        top_values: Any = None,
        scope_definition: Any = None,
    ) -> int:
        connection = self.connect()
        try:
            attribute_id = self._attribute_id(connection, attribute_key)
            row = connection.execute(
                """
                INSERT INTO AttributeStats (
                    attribute_id, scope_hash, scope_definition, data_revision,
                    row_count, non_null_count, null_count, distinct_count,
                    min_value, max_value, mean_value, stddev_value, median_value,
                    q1_value, q3_value, min_text, max_text, top_values
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (attribute_id, scope_hash, data_revision) DO UPDATE SET
                    scope_definition = excluded.scope_definition,
                    row_count = excluded.row_count,
                    non_null_count = excluded.non_null_count,
                    null_count = excluded.null_count,
                    distinct_count = excluded.distinct_count,
                    min_value = excluded.min_value,
                    max_value = excluded.max_value,
                    mean_value = excluded.mean_value,
                    stddev_value = excluded.stddev_value,
                    median_value = excluded.median_value,
                    q1_value = excluded.q1_value,
                    q3_value = excluded.q3_value,
                    min_text = excluded.min_text,
                    max_text = excluded.max_text,
                    top_values = excluded.top_values,
                    computed_at = now()
                RETURNING stat_id
                """,
                [
                    attribute_id, scope_hash, _json_value(scope_definition),
                    data_revision, row_count, non_null_count, null_count,
                    distinct_count, min_value, max_value, mean_value,
                    stddev_value, median_value, q1_value, q3_value, min_text,
                    max_text, _json_value(top_values),
                ],
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def get_stats(
        self, attribute_key: str, scope_hash: str, data_revision: str
    ) -> dict[str, Any] | None:
        connection = self.connect(read_only=True)
        try:
            cursor = connection.execute(
                """
                SELECT stats.*
                FROM AttributeStats stats
                JOIN Attributes attribute USING (attribute_id)
                WHERE attribute.attribute_key = ? AND scope_hash = ?
                  AND data_revision = ?
                  AND (expires_at IS NULL OR expires_at > now())
                """,
                [attribute_key, scope_hash, data_revision],
            )
            rows = _rows_as_dicts(cursor)
            if not rows:
                return None
            return _decode_json_fields(rows[0], ("scope_definition", "top_values"))
        finally:
            connection.close()

    @staticmethod
    def _attribute_id(
        connection: duckdb.DuckDBPyConnection, attribute_key: str
    ) -> int:
        row = connection.execute(
            "SELECT attribute_id FROM Attributes WHERE attribute_key = ?",
            [attribute_key],
        ).fetchone()
        if row is None:
            raise RegistryError(f"Unknown attribute_key: {attribute_key}")
        return int(row[0])

    @staticmethod
    def _find_column(columns: list[str], candidates: Iterable[str]) -> str | None:
        by_lower = {column.lower(): column for column in columns}
        for candidate in candidates:
            if candidate.lower() in by_lower:
                return by_lower[candidate.lower()]
        return None

    @staticmethod
    def _reader_columns(
        connection: duckdb.DuckDBPyConnection, reader_sql: str
    ) -> list[str]:
        cursor = connection.execute(f"SELECT * FROM {reader_sql} LIMIT 0")
        return [item[0] for item in cursor.description]

    @staticmethod
    def _reader_sql(path: Path, *, all_varchar: bool) -> tuple[str, str]:
        if any(character in str(path) for character in "*?[]"):
            raise RegistryError(
                "Input paths containing DuckDB glob metacharacters are unsupported"
            )
        suffix = path.suffix.lower()
        literal = _sql_literal(str(path))
        if suffix == ".parquet":
            return "parquet", f"read_parquet({literal})"
        if suffix in {".csv", ".tsv", ".txt"}:
            delimiter = "'\\t'" if suffix == ".tsv" else "','"
            return (
                "csv",
                f"read_csv_auto({literal}, header=true, delim={delimiter}, "
                f"all_varchar={str(all_varchar).lower()})",
            )
        raise RegistryError(f"Unsupported file format: {suffix}")

    @staticmethod
    def _value_type(duckdb_type: str) -> str:
        normalized = duckdb_type.upper()
        if "BOOL" in normalized:
            return "boolean"
        if any(token in normalized for token in ("INT", "HUGEINT", "UBIGINT")):
            return "integer"
        if any(token in normalized for token in ("FLOAT", "DOUBLE", "DECIMAL", "REAL")):
            return "float"
        if "JSON" in normalized or normalized.startswith(("STRUCT", "MAP", "LIST")):
            return "json"
        return "string"

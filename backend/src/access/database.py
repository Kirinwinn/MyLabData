"""DuckDB connection and transaction access for the third-version DryData file."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from access.paths import DryDataPaths


class DryDataDatabaseError(RuntimeError):
    """Raised when the configured core DryData database cannot be used."""


class DryDataSchemaError(DryDataDatabaseError):
    """Raised when the file is not shaped like the supported third-version schema."""


REQUIRED_V3_COLUMNS: dict[str, frozenset[str]] = {
    "Molecules": frozenset({"molecule_id", "lab_id", "canonical_smiles", "channel", "created_at"}),
    "Attributes": frozenset(
        {"attribute_id", "attribute_key", "attribute_name", "value_type", "unit", "description"}
    ),
    "Entries": frozenset(
        {
            "entry_id",
            "attribute_id",
            "entry_key",
            "annotation_kind",
            "method_name",
            "method_version",
            "conditions_json",
            "is_mutable",
            "description",
        }
    ),
    "Annotations": frozenset(
        {
            "molecule_id",
            "entry_id",
            "value_number",
            "value_text",
            "value_boolean",
            "created_at",
            "updated_at",
        }
    ),
    "Sources": frozenset({"source_id", "source_key", "source_type", "description"}),
    "Imports": frozenset(
        {
            "import_id",
            "source_id",
            "file_hash",
            "data_type",
            "status",
            "processor",
            "total_rows",
            "error_message",
            "created_at",
            "finished_at",
        }
    ),
}


class DryDataDatabase:
    """Open the canonical DryData database without applying legacy migrations."""

    def __init__(self, paths: DryDataPaths, *, config: dict[str, str] | None = None) -> None:
        self.paths = paths
        self.config = config or {}

    @contextmanager
    def connection(self, *, read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield one short-lived DuckDB connection and always close it."""
        database_path = self.paths.database_path
        if not database_path.is_file():
            raise DryDataDatabaseError(f"DryData database does not exist: {database_path}")
        try:
            connection = duckdb.connect(
                str(database_path),
                read_only=read_only,
                config=self.config,
            )
        except duckdb.Error as exc:
            raise DryDataDatabaseError(f"Cannot open DryData database: {exc}") from exc
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield one writable connection with commit-or-rollback semantics."""
        with self.connection(read_only=False) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                yield connection
            except Exception:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")

    def verify_v3_schema(self) -> dict[str, set[str]]:
        """Verify the six supported third-version tables and their required columns."""
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'main'
                """
            ).fetchall()

        discovered: dict[str, set[str]] = {}
        for table_name, column_name in rows:
            discovered.setdefault(str(table_name), set()).add(str(column_name))

        errors = []
        for table_name, required in REQUIRED_V3_COLUMNS.items():
            missing = required - discovered.get(table_name, set())
            if missing:
                errors.append(f"{table_name} is missing {sorted(missing)}")
        if errors:
            raise DryDataSchemaError("; ".join(errors))
        return discovered

    @property
    def database_path(self) -> Path:
        return self.paths.database_path

    def database_settings(self) -> dict[str, Any]:
        """Return effective DuckDB settings for diagnostics."""
        with self.connection() as connection:
            names = ("memory_limit", "threads", "temp_directory")
            return {
                name: connection.execute("SELECT current_setting(?)", [name]).fetchone()[0]
                for name in names
            }

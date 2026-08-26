"""DuckDB connection creation, configuration, and cleanup."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import DatabaseConnectionError


def _connection_config(settings: Settings) -> dict[str, str]:
    """Build the DuckDB configuration passed at connection creation."""
    return {
        "memory_limit": settings.memory_limit,
        "temp_directory": str(settings.resolved_temp_directory),
        "threads": str(settings.threads),
        "preserve_insertion_order": str(settings.preserve_insertion_order).lower(),
    }


def _prepare_paths(settings: Settings, *, read_only: bool) -> Path:
    """Prepare writable directories and return the database path."""
    database_path = settings.resolved_database_path

    if read_only and not database_path.is_file():
        raise DatabaseConnectionError(
            f"Cannot open missing DuckDB database in read-only mode: {database_path}"
        )

    if not read_only:
        database_path.parent.mkdir(parents=True, exist_ok=True)

    # Read-only queries can still spill intermediate results to disk.
    settings.resolved_temp_directory.mkdir(parents=True, exist_ok=True)
    return database_path


def open_connection(
    settings: Settings | None = None,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open and configure one explicit DuckDB connection.

    The caller owns the returned connection and must close it. Prefer the
    ``connection`` context manager for ordinary use.
    """
    resolved_settings = settings or get_settings()
    database_path = _prepare_paths(resolved_settings, read_only=read_only)

    try:
        return duckdb.connect(
            database=str(database_path),
            read_only=read_only,
            config=_connection_config(resolved_settings),
        )
    except (duckdb.Error, OSError, ValueError) as exc:
        raise DatabaseConnectionError(
            f"Unable to open DuckDB database at {database_path}: {exc}"
        ) from exc


@contextmanager
def connection(
    settings: Settings | None = None,
    *,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a configured connection and always close it afterwards."""
    database_connection = open_connection(settings, read_only=read_only)
    try:
        yield database_connection
    finally:
        database_connection.close()


def current_database_settings(
    database_connection: duckdb.DuckDBPyConnection,
) -> dict[str, Any]:
    """Return the effective resource settings for diagnostics and tests."""
    names = (
        "memory_limit",
        "temp_directory",
        "threads",
        "preserve_insertion_order",
    )
    return {
        name: database_connection.execute(
            "SELECT current_setting(?)",
            [name],
        ).fetchone()[0]
        for name in names
    }

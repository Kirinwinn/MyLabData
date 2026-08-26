"""File-based DuckDB schema migrations with checksum verification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import duckdb

from mylabdata.core.config import Settings
from mylabdata.core.exceptions import (
    MigrationChecksumError,
    MigrationError,
    MigrationHistoryError,
)
from mylabdata.db.connection import connection

MIGRATION_FILE_PATTERN = re.compile(
    r"^(?P<version>[0-9]{3,})_(?P<name>[a-z0-9][a-z0-9_]*)[.]sql$"
)
MIGRATIONS_TABLE = "_schema_migrations"
DEFAULT_MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable SQL migration loaded from disk."""

    version: int
    name: str
    path: Path
    sql: str
    checksum: str


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One migration recorded in the database."""

    version: int
    name: str
    checksum: str


def discover_migrations(
    migrations_directory: Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> list[Migration]:
    """Load valid migration files in ascending version order."""
    if not migrations_directory.is_dir():
        raise MigrationError(f"Migration directory does not exist: {migrations_directory}")

    migrations: list[Migration] = []
    versions: set[int] = set()

    for path in sorted(migrations_directory.glob("*.sql")):
        match = MIGRATION_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationError(
                "Invalid migration filename. Expected "
                f"NNN_lowercase_name.sql, received: {path.name}"
            )

        version = int(match.group("version"))
        if version in versions:
            raise MigrationError(f"Duplicate migration version {version}: {path.name}")

        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise MigrationError(f"Migration file is empty: {path}")

        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                sql=sql,
                checksum=sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
        versions.add(version)

    migrations.sort(key=lambda item: item.version)
    return migrations


def ensure_migrations_table(database_connection: duckdb.DuckDBPyConnection) -> None:
    """Create the internal schema history table when absent."""
    database_connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (
            version INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            checksum VARCHAR NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def migrations_table_exists(database_connection: duckdb.DuckDBPyConnection) -> bool:
    """Return whether the internal schema history table is present."""
    row = database_connection.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        """,
        [MIGRATIONS_TABLE],
    ).fetchone()
    return bool(row[0])


def get_applied_migrations(
    database_connection: duckdb.DuckDBPyConnection,
) -> list[AppliedMigration]:
    """Return migrations recorded in the database."""
    if not migrations_table_exists(database_connection):
        return []
    rows = database_connection.execute(
        f"""
        SELECT version, name, checksum
        FROM {MIGRATIONS_TABLE}
        ORDER BY version
        """
    ).fetchall()
    return [AppliedMigration(*row) for row in rows]


def get_schema_version(database_connection: duckdb.DuckDBPyConnection) -> int:
    """Return the highest applied schema version, or zero for a new database."""
    if not migrations_table_exists(database_connection):
        return 0
    row = database_connection.execute(
        f"SELECT COALESCE(MAX(version), 0) FROM {MIGRATIONS_TABLE}"
    ).fetchone()
    return int(row[0])


def _validate_history(
    available: list[Migration],
    applied: list[AppliedMigration],
) -> list[Migration]:
    """Validate recorded history and return migrations still pending."""
    available_by_version = {migration.version: migration for migration in available}
    applied_versions = {migration.version for migration in applied}

    for recorded in applied:
        migration = available_by_version.get(recorded.version)
        if migration is None:
            raise MigrationHistoryError(
                f"Applied migration {recorded.version:03d}_{recorded.name}.sql is missing"
            )
        if migration.name != recorded.name:
            raise MigrationHistoryError(
                f"Migration {recorded.version:03d} was renamed from "
                f"{recorded.name!r} to {migration.name!r}"
            )
        if migration.checksum != recorded.checksum:
            raise MigrationChecksumError(
                f"Applied migration was modified: {migration.path.name}"
            )

    current_version = max(applied_versions, default=0)
    pending = [migration for migration in available if migration.version not in applied_versions]
    late = [migration for migration in pending if migration.version <= current_version]
    if late:
        names = ", ".join(migration.path.name for migration in late)
        raise MigrationHistoryError(
            f"Migrations were inserted behind schema version {current_version}: {names}"
        )
    return pending


def apply_migration(
    database_connection: duckdb.DuckDBPyConnection,
    migration: Migration,
) -> None:
    """Apply one migration and record it in the same transaction."""
    database_connection.execute("BEGIN TRANSACTION")
    try:
        database_connection.execute(migration.sql)
        database_connection.execute(
            f"""
            INSERT INTO {MIGRATIONS_TABLE} (version, name, checksum)
            VALUES (?, ?, ?)
            """,
            [migration.version, migration.name, migration.checksum],
        )
        database_connection.execute("COMMIT")
    except Exception as exc:
        database_connection.execute("ROLLBACK")
        raise MigrationError(f"Failed to apply migration {migration.path.name}: {exc}") from exc


def migrate_connection(
    database_connection: duckdb.DuckDBPyConnection,
    migrations_directory: Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> int:
    """Apply all pending migrations and return the resulting schema version."""
    available = discover_migrations(migrations_directory)
    ensure_migrations_table(database_connection)
    applied = get_applied_migrations(database_connection)

    for migration in _validate_history(available, applied):
        apply_migration(database_connection, migration)

    return get_schema_version(database_connection)


def migrate(
    settings: Settings | None = None,
    migrations_directory: Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> int:
    """Open the configured database, apply migrations, and close it."""
    with connection(settings) as database_connection:
        return migrate_connection(database_connection, migrations_directory)

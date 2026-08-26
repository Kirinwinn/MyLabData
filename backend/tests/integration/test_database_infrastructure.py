"""Integration tests for DuckDB connections and schema migrations."""

from pathlib import Path

import duckdb
import pytest

from mylabdata.core.config import Settings
from mylabdata.core.exceptions import (
    DatabaseConnectionError,
    MigrationChecksumError,
    MigrationError,
)
from mylabdata.db.connection import connection, current_database_settings
from mylabdata.db.migrate import get_schema_version, migrate


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path / "DryData",
        memory_limit="1GB",
        threads=1,
    )


def test_connection_creates_paths_and_applies_settings(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    with connection(settings) as database_connection:
        effective = current_database_settings(database_connection)
        assert database_connection.execute("SELECT 42").fetchone() == (42,)

    assert settings.resolved_database_path.is_file()
    assert settings.resolved_temp_directory.is_dir()
    assert int(effective["threads"]) == 1
    assert effective["preserve_insertion_order"] is False
    assert Path(effective["temp_directory"]).resolve() == (
        settings.resolved_temp_directory.resolve()
    )


def test_read_only_connection_requires_existing_database(tmp_path: Path) -> None:
    with pytest.raises(DatabaseConnectionError, match="missing DuckDB database"):
        with connection(make_settings(tmp_path), read_only=True):
            pass


def test_empty_migration_directory_initializes_version_zero(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrations_directory = tmp_path / "migrations"
    migrations_directory.mkdir()

    assert migrate(settings, migrations_directory) == 0

    with connection(settings, read_only=True) as database_connection:
        assert get_schema_version(database_connection) == 0


def test_migrations_apply_once_and_record_version(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrations_directory = tmp_path / "migrations"
    migrations_directory.mkdir()
    (migrations_directory / "001_example.sql").write_text(
        "CREATE TABLE example (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )

    assert migrate(settings, migrations_directory) == 1
    assert migrate(settings, migrations_directory) == 1

    with connection(settings, read_only=True) as database_connection:
        assert get_schema_version(database_connection) == 1
        assert database_connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'example'"
        ).fetchone() == (1,)
        assert database_connection.execute(
            "SELECT COUNT(*) FROM _schema_migrations"
        ).fetchone() == (1,)


def test_modified_applied_migration_is_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrations_directory = tmp_path / "migrations"
    migrations_directory.mkdir()
    migration_path = migrations_directory / "001_example.sql"
    migration_path.write_text("CREATE TABLE example (id INTEGER);\n", encoding="utf-8")
    migrate(settings, migrations_directory)

    migration_path.write_text(
        "CREATE TABLE example (id INTEGER, name VARCHAR);\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationChecksumError, match="Applied migration was modified"):
        migrate(settings, migrations_directory)


def test_failed_migration_rolls_back_sql_and_history(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrations_directory = tmp_path / "migrations"
    migrations_directory.mkdir()
    (migrations_directory / "001_stable.sql").write_text(
        "CREATE TABLE stable (id INTEGER);\n",
        encoding="utf-8",
    )
    (migrations_directory / "002_broken.sql").write_text(
        "CREATE TABLE should_rollback (id INTEGER);\n"
        "INSERT INTO table_that_does_not_exist VALUES (1);\n",
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="002_broken.sql"):
        migrate(settings, migrations_directory)

    with connection(settings) as database_connection:
        assert get_schema_version(database_connection) == 1
        assert database_connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'should_rollback'"
        ).fetchone() == (0,)


def test_connection_context_closes_connection(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    with connection(settings) as database_connection:
        assert database_connection.execute("SELECT 1").fetchone() == (1,)

    with pytest.raises(duckdb.ConnectionException):
        database_connection.execute("SELECT 1")

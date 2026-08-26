"""Tests for file-based migration discovery."""

from hashlib import sha256
from pathlib import Path

import pytest

from mylabdata.core.exceptions import MigrationError
from mylabdata.db.migrate import discover_migrations


def test_discovers_migrations_in_version_order(tmp_path: Path) -> None:
    second_sql = "CREATE TABLE second_table (id INTEGER);\n"
    first_sql = "CREATE TABLE first_table (id INTEGER);\n"
    (tmp_path / "002_second.sql").write_text(second_sql, encoding="utf-8")
    (tmp_path / "001_first.sql").write_text(first_sql, encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2]
    assert migrations[0].name == "first"
    assert migrations[0].checksum == sha256(first_sql.encode("utf-8")).hexdigest()


def test_rejects_invalid_migration_filename(tmp_path: Path) -> None:
    (tmp_path / "1-Bad-Name.sql").write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(MigrationError, match="Invalid migration filename"):
        discover_migrations(tmp_path)


def test_rejects_duplicate_numeric_version(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0001_duplicate.sql").write_text("SELECT 2;", encoding="utf-8")

    with pytest.raises(MigrationError, match="Duplicate migration version"):
        discover_migrations(tmp_path)


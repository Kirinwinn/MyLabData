"""Tests for backend path configuration."""

from pathlib import Path

from mylabdata.core.config import Settings


def test_default_database_and_temp_paths(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path)

    assert settings.resolved_database_path == tmp_path / "Registry" / "mylabdata.duckdb"
    assert settings.resolved_temp_directory == tmp_path / "Temp"


def test_database_and_temp_paths_can_be_overridden(tmp_path: Path) -> None:
    database_path = tmp_path / "custom" / "database.duckdb"
    temp_directory = tmp_path / "custom-temp"
    settings = Settings(
        data_root=tmp_path / "data",
        database_path=database_path,
        temp_directory=temp_directory,
    )

    assert settings.resolved_database_path == database_path
    assert settings.resolved_temp_directory == temp_directory


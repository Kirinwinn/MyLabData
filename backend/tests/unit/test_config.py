"""Tests for backend path configuration."""

from pathlib import Path

from core.config import Settings


def test_default_database_and_temp_paths(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path)

    assert settings.resolved_database_path == tmp_path / "DryData.duckdb"
    assert settings.resolved_jobs_database_path == tmp_path / "Jobs.duckdb"
    assert settings.resolved_temp_directory == tmp_path / "Temp"


def test_all_data_paths_are_derived_from_one_root(tmp_path: Path) -> None:
    root = tmp_path / "data"
    settings = Settings(data_root=root)

    assert settings.resolved_database_path == root / "DryData.duckdb"
    assert settings.resolved_jobs_database_path == root / "Jobs.duckdb"
    assert settings.resolved_temp_directory == root / "Temp"

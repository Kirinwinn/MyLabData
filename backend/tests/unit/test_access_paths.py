"""Tests for the single-root DryData path contract."""

from pathlib import Path

from access.paths import DryDataPaths


def test_all_runtime_paths_are_derived_from_one_root(tmp_path: Path) -> None:
    paths = DryDataPaths(tmp_path / "DryData")

    assert paths.database_path == paths.root / "DryData.duckdb"
    assert paths.jobs_database_path == paths.root / "Jobs.duckdb"
    assert paths.cache_directory == paths.root / "Cache"
    assert paths.temp_directory == paths.root / "Temp"
    assert paths.new_directory == paths.root / "New"
    assert set(paths.runtime_directories()) == {
        paths.root / "Incoming" / "Molecules",
        paths.root / "Incoming" / "Annotations",
        paths.root / "Processed" / "Molecules",
        paths.root / "Processed" / "Annotations",
        paths.root / "Failed" / "Molecules",
        paths.root / "Failed" / "Annotations",
        paths.root / "Cache",
        paths.root / "Temp",
        paths.root / "New",
    }


def test_runtime_directory_creation_does_not_create_database_files(tmp_path: Path) -> None:
    paths = DryDataPaths(tmp_path / "DryData")

    paths.ensure_runtime_directories()

    assert all(directory.is_dir() for directory in paths.runtime_directories())
    assert not paths.database_path.exists()
    assert not paths.jobs_database_path.exists()

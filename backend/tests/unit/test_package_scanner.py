"""Tests for Incoming/Molecules file discovery."""

from pathlib import Path

from mylabdata.core.config import Settings
from mylabdata.services.package_scanner import get_package, scan_molecule_files, scan_packages


def test_scanner_returns_only_top_level_parquet_files(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData")
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True)
    (incoming / "b.PARQUET").write_bytes(b"b")
    (incoming / "a.parquet").write_bytes(b"a")
    (incoming / "notes.txt").write_text("ignore", encoding="utf-8")
    nested = incoming / "nested"
    nested.mkdir()
    (nested / "nested.parquet").write_bytes(b"ignore")

    candidates = scan_molecule_files(settings)

    assert [candidate.file_name for candidate in candidates] == [
        "a.parquet",
        "b.PARQUET",
    ]
    assert [candidate.size_bytes for candidate in candidates] == [1, 1]


def test_public_packages_use_opaque_ids_instead_of_paths(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData")
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True)
    file_path = incoming / "molecules.parquet"
    file_path.write_bytes(b"parquet-placeholder")

    packages = scan_packages(settings)

    assert len(packages) == 1
    assert packages[0].package_id.startswith("mol_")
    assert "\\" not in packages[0].package_id
    detail, resolved = get_package(packages[0].package_id, settings)
    assert detail.files == ["molecules.parquet"]
    assert resolved == file_path.resolve()


def test_scanner_returns_empty_list_when_directory_is_absent(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData")

    assert scan_molecule_files(settings) == []

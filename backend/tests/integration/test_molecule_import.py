"""Integration tests for Molecules preview and transactional import."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from mylabdata.core.config import Settings
from mylabdata.core.exceptions import MoleculeFileError, MoleculeImportError
from mylabdata.db.connection import connection
from mylabdata.db.migrate import migrate
from mylabdata.services import molecule_importer
from mylabdata.services.molecule_importer import (
    import_molecule_file,
    preview_molecule_file,
)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)


def write_molecule_file(
    settings: Settings,
    name: str,
    values: list[str | None],
) -> Path:
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True, exist_ok=True)
    file_path = incoming / name
    pq.write_table(
        pa.table({"canonical_smiles": pa.array(values, type=pa.string())}),
        file_path,
    )
    return file_path


def test_preview_distinguishes_all_required_counts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    with connection(settings) as database_connection:
        database_connection.execute(
            "INSERT INTO Molecules (lab_id, canonical_smiles) VALUES ('L00000001', 'CCO')"
        )
    file_path = write_molecule_file(
        settings,
        "preview.parquet",
        ["CCO", "CCN", "CCO", " ", None, " CCC "],
    )

    preview = preview_molecule_file(file_path, settings)

    assert preview.total_rows == 6
    assert preview.valid_rows == 4
    assert preview.new_rows == 2
    assert preview.existing_rows == 1
    assert preview.duplicate_rows == 1
    assert preview.invalid_rows == 2
    assert len(preview.file_hash) == 64


def test_import_inserts_distinct_molecules_and_records_audit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    file_path = write_molecule_file(
        settings,
        "molecules.parquet",
        ["CCO", "CCN", "CCO", " ", None, " CCC "],
    )
    preview = preview_molecule_file(file_path, settings)

    result = import_molecule_file(
        file_path,
        settings,
        expected_file_hash=preview.file_hash,
    )

    assert result.total_rows == 6
    assert result.valid_rows == 4
    assert result.new_rows == 3
    assert result.existing_rows == 0
    assert result.duplicate_rows == 1
    assert result.invalid_rows == 2
    assert result.inserted_rows == 3

    with connection(settings, read_only=True) as database_connection:
        molecules = database_connection.execute(
            """
            SELECT molecule_id, lab_id, canonical_smiles
            FROM Molecules
            """
        ).fetchall()
        audit = database_connection.execute(
            """
            SELECT file_name, file_hash, data_type, status,
                   total_rows, valid_rows, new_rows, existing_rows,
                   duplicate_rows, accepted_rows, failed_rows
            FROM Imports
            WHERE import_id = ?
            """,
            [result.import_id],
        ).fetchone()

    assert {row[2] for row in molecules} == {"CCO", "CCN", "CCC"}
    assert all(
        lab_id == f"L{molecule_id:08d}"
        for molecule_id, lab_id, _ in molecules
    )
    assert audit == (
        "molecules.parquet",
        preview.file_hash,
        "molecules",
        "completed",
        6,
        4,
        3,
        0,
        1,
        3,
        2,
    )


def test_reimport_is_idempotent_and_audited(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    file_path = write_molecule_file(
        settings,
        "repeat.parquet",
        ["CCO", "CCN", "CCO"],
    )

    first = import_molecule_file(file_path, settings)
    second = import_molecule_file(file_path, settings)

    assert first.inserted_rows == 2
    assert second.inserted_rows == 0
    assert second.new_rows == 0
    assert second.existing_rows == 2
    assert second.duplicate_rows == 1
    assert first.file_hash == second.file_hash

    with connection(settings, read_only=True) as database_connection:
        molecule_count = database_connection.execute(
            "SELECT count(*) FROM Molecules"
        ).fetchone()[0]
        imports = database_connection.execute(
            """
            SELECT status, accepted_rows, file_hash
            FROM Imports
            ORDER BY import_id
            """
        ).fetchall()

    assert molecule_count == 2
    assert imports == [
        ("completed", 2, first.file_hash),
        ("completed", 0, first.file_hash),
    ]


def test_failure_rolls_back_molecules_and_preserves_failed_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    file_path = write_molecule_file(settings, "rollback.parquet", ["CCO", "CCN"])

    def fail_completion(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected completion failure")

    monkeypatch.setattr(molecule_importer, "complete_molecule_import", fail_completion)

    with pytest.raises(MoleculeImportError, match="rolled back"):
        import_molecule_file(file_path, settings)

    with connection(settings, read_only=True) as database_connection:
        molecule_count = database_connection.execute(
            "SELECT count(*) FROM Molecules"
        ).fetchone()[0]
        audit = database_connection.execute(
            """
            SELECT status, accepted_rows, failed_rows, error_message
            FROM Imports
            """
        ).fetchone()

    assert molecule_count == 0
    assert audit[:3] == ("failed", 0, 2)
    assert "injected completion failure" in audit[3]


def test_missing_required_column_is_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True)
    file_path = incoming / "wrong-schema.parquet"
    pq.write_table(pa.table({"SMILES": ["CCO"]}), file_path)

    with pytest.raises(MoleculeFileError, match="canonical_smiles"):
        preview_molecule_file(file_path, settings)


def test_non_string_canonical_smiles_is_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True)
    file_path = incoming / "wrong-type.parquet"
    pq.write_table(pa.table({"canonical_smiles": [1, 2]}), file_path)

    with pytest.raises(MoleculeFileError, match="must be VARCHAR"):
        preview_molecule_file(file_path, settings)


def test_hash_mismatch_prevents_import(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    file_path = write_molecule_file(settings, "hash.parquet", ["CCO"])

    with pytest.raises(MoleculeFileError, match="hash"):
        import_molecule_file(file_path, settings, expected_file_hash="0" * 64)

    with connection(settings, read_only=True) as database_connection:
        assert database_connection.execute(
            "SELECT count(*) FROM Molecules"
        ).fetchone() == (0,)
        assert database_connection.execute(
            "SELECT count(*) FROM Imports"
        ).fetchone() == (0,)


def test_file_outside_incoming_directory_is_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    file_path = tmp_path / "outside.parquet"
    pq.write_table(pa.table({"canonical_smiles": ["CCO"]}), file_path)

    with pytest.raises(MoleculeFileError, match="must be inside"):
        preview_molecule_file(file_path, settings)

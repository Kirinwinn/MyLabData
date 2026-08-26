"""Integration tests for non-mutating Annotation Package preview."""

import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from mylabdata.core.config import Settings
from mylabdata.core.exceptions import (
    AnnotationImportError,
    AnnotationPackageError,
    PreviewTokenError,
)
from mylabdata.db.connection import connection
from mylabdata.db.migrate import migrate
from mylabdata.services import annotation_importer
from mylabdata.services.annotation_importer import import_annotation_package
from mylabdata.services.annotation_preview import (
    assert_annotation_preview_current,
    preview_annotation_package,
)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)


def write_package(settings: Settings) -> Path:
    package = settings.incoming_annotations_directory / "rdkit-001"
    package.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "processor_name": "RDKitAdapter",
        "processor_version": "1.0",
        "attributes": [
            {
                "attribute_key": "emission_wavelength",
                "attribute_name": "Emission Wavelength",
                "value_type": "number",
                "unit": "nm",
                "description": "Emission wavelength",
            },
            {
                "attribute_key": "plqy",
                "attribute_name": "PLQY",
                "value_type": "number",
                "unit": None,
                "description": "Quantum yield",
            },
        ],
        "entries": [
            {
                "entry_key": "emission_wavelength.proby.dmso",
                "attribute_key": "emission_wavelength",
                "annotation_kind": "prediction",
                "method_name": "Proby",
                "method_version": "1.0",
                "conditions": {"solvent_name": "DMSO"},
                "source_key": None,
                "is_mutable": False,
                "description": "Proby in DMSO",
            },
            {
                "entry_key": "plqy.rdkit",
                "attribute_key": "plqy",
                "annotation_kind": "calculation",
                "method_name": "RDKit",
                "method_version": "1.0",
                "conditions": {},
                "source_key": None,
                "is_mutable": False,
                "description": "Calculated PLQY",
            },
        ],
        "data_files": ["annotations.parquet"],
        "generated_at": "2026-08-26T10:00:00+08:00",
    }
    report = {
        "status": "completed",
        "input_rows": 4,
        "output_annotations": 4,
        "rejected_rows": 0,
        "duplicate_rows": 1,
        "warnings": [],
        "started_at": "2026-08-26T10:00:00+08:00",
        "finished_at": "2026-08-26T10:01:00+08:00",
    }
    (package / "annotation_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (package / "processing_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    pq.write_table(
        pa.table(
            {
                "canonical_smiles": pa.array(["CCO", "CCN", "CCN", "CCC"], pa.string()),
                "attribute_key": pa.array(
                    ["emission_wavelength", "plqy", "plqy", "plqy"], pa.string()
                ),
                "entry_key": pa.array(
                    [
                        "emission_wavelength.proby.dmso",
                        "plqy.rdkit",
                        "plqy.rdkit",
                        "plqy.rdkit",
                    ],
                    pa.string(),
                ),
                "value_number": pa.array([520.0, 0.5, 0.5, 0.7], pa.float64()),
                "value_text": pa.array([None] * 4, pa.string()),
                "value_boolean": pa.array([None] * 4, pa.bool_()),
            }
        ),
        package / "annotations.parquet",
    )
    return package


def seed_catalog(settings: Settings) -> None:
    migrate(settings)
    with connection(settings) as database_connection:
        database_connection.execute(
            """
            INSERT INTO Molecules (lab_id, canonical_smiles)
            VALUES ('L00000001', 'CCO'), ('L00000002', 'CCN')
            """
        )
        database_connection.execute(
            """
            INSERT INTO Attributes (
                attribute_key, attribute_name, value_type, unit, description
            ) VALUES (
                'emission_wavelength', 'Emission Wavelength', 'number', 'nm',
                'Emission wavelength'
            )
            """
        )
        database_connection.execute(
            """
            INSERT INTO Entries (
                attribute_id, entry_key, annotation_kind, method_name,
                method_version, conditions_json, description
            )
            SELECT attribute_id, 'emission_wavelength.proby.dmso',
                   'prediction', 'Proby', '1.0',
                   '{"solvent_name":"DMSO"}', 'Proby in DMSO'
            FROM Attributes WHERE attribute_key = 'emission_wavelength'
            """
        )
        database_connection.execute(
            """
            INSERT INTO Annotations (molecule_id, entry_id, value_number)
            SELECT molecule_id, entry_id, 519.0
            FROM Molecules CROSS JOIN Entries
            WHERE canonical_smiles = 'CCO'
              AND entry_key = 'emission_wavelength.proby.dmso'
            """
        )


def test_preview_is_complete_and_does_not_modify_business_tables(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    with connection(settings, read_only=True) as database_connection:
        before = database_connection.execute(
            """
            SELECT (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()

    preview = preview_annotation_package(package, settings)

    assert [(item.definition.attribute_key, item.status) for item in preview.attributes] == [
        ("emission_wavelength", "existing"),
        ("plqy", "new"),
    ]
    assert [(item.definition.entry_key, item.status) for item in preview.entries] == [
        ("emission_wavelength.proby.dmso", "existing"),
        ("plqy.rdkit", "new"),
    ]
    assert preview.annotation_rows == 4
    assert preview.linkable_molecules == 2
    assert preview.unlinkable_molecules == 1
    assert preview.duplicate_annotations == 1
    assert preview.existing_annotations == 1
    assert preview.expected_inserts == 1
    assert preview.can_import
    assert_annotation_preview_current(package, preview.preview_token, settings)

    with connection(settings, read_only=True) as database_connection:
        after = database_connection.execute(
            """
            SELECT (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()
    assert after == before


def test_conflicting_attribute_is_explicit_error(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    manifest_path = package / "annotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["attributes"][0]["unit"] = "eV"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    preview = preview_annotation_package(package, settings)

    assert preview.attributes[0].status == "conflict"
    assert preview.attributes[0].conflicts == ["unit"]
    assert not preview.can_import
    assert any("conflicting Attribute" in error for error in preview.errors)


def test_conflicting_entry_is_explicit_error(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    manifest_path = package / "annotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["method_version"] = "2.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    preview = preview_annotation_package(package, settings)

    assert preview.entries[0].status == "conflict"
    assert preview.entries[0].conflicts == ["method_version"]
    assert not preview.can_import
    assert any("conflicting Entry" in error for error in preview.errors)


def test_annotation_value_type_error_is_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    pq.write_table(
        pa.table(
            {
                "canonical_smiles": pa.array(["CCO"], pa.string()),
                "attribute_key": pa.array(["emission_wavelength"], pa.string()),
                "entry_key": pa.array(
                    ["emission_wavelength.proby.dmso"], pa.string()
                ),
                "value_number": pa.array([None], pa.float64()),
                "value_text": pa.array(["not-a-number"], pa.string()),
                "value_boolean": pa.array([None], pa.bool_()),
            }
        ),
        package / "annotations.parquet",
    )
    report_path = package / "processing_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.update(input_rows=1, output_annotations=1, duplicate_rows=0)
    report_path.write_text(json.dumps(report), encoding="utf-8")

    preview = preview_annotation_package(package, settings)

    assert not preview.can_import
    assert preview.expected_inserts == 0
    assert any("1 invalid rows" in error for error in preview.errors)


def test_changed_package_invalidates_preview_token(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    preview = preview_annotation_package(package, settings)
    report_path = package / "processing_report.json"
    report_path.write_text(report_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(PreviewTokenError, match="changed"):
        assert_annotation_preview_current(package, preview.preview_token, settings)


def test_annotation_import_is_atomic_and_moves_package_after_commit(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    preview = preview_annotation_package(package, settings)

    result = import_annotation_package(package, preview.preview_token, settings)

    assert result.inserted_annotations == preview.expected_inserts == 1
    assert result.unlinkable_molecules == preview.unlinkable_molecules == 1
    assert result.created_attributes == 1
    assert result.created_entries == 1
    assert result.package_moved
    assert not package.exists()
    assert (settings.data_root / result.destination).is_dir()
    with connection(settings, read_only=True) as database_connection:
        counts = database_connection.execute(
            """
            SELECT (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()
        missing_molecule_annotations = database_connection.execute(
            """
            SELECT count(*) FROM Annotations AS annotation
            JOIN Molecules AS molecule USING (molecule_id)
            WHERE molecule.canonical_smiles = 'CCC'
            """
        ).fetchone()
    assert counts == (2, 2, 2, 1)
    assert missing_molecule_annotations == (0,)


def test_reimport_is_idempotent_and_audited(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    first_package = write_package(settings)
    first_preview = preview_annotation_package(first_package, settings)
    first = import_annotation_package(
        first_package,
        first_preview.preview_token,
        settings,
    )
    second_package = settings.incoming_annotations_directory / "rdkit-002"
    shutil.copytree(settings.data_root / first.destination, second_package)
    second_preview = preview_annotation_package(second_package, settings)

    second = import_annotation_package(
        second_package,
        second_preview.preview_token,
        settings,
    )

    assert second.inserted_annotations == 0
    assert second.created_attributes == 0
    assert second.created_entries == 0
    assert second.package_hash == first.package_hash
    with connection(settings, read_only=True) as database_connection:
        assert database_connection.execute(
            "SELECT count(*) FROM Annotations"
        ).fetchone() == (2,)
        assert database_connection.execute(
            "SELECT accepted_rows FROM Imports ORDER BY import_id"
        ).fetchall() == [(1,), (0,)]


def test_database_failure_rolls_back_and_keeps_package_in_incoming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    preview = preview_annotation_package(package, settings)

    def fail_audit(*args: object, **kwargs: object) -> int:
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(annotation_importer, "create_annotation_import", fail_audit)
    with pytest.raises(AnnotationImportError, match="rolled back"):
        import_annotation_package(package, preview.preview_token, settings)

    assert package.is_dir()
    with connection(settings, read_only=True) as database_connection:
        counts = database_connection.execute(
            """
            SELECT (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()
    assert counts == (1, 1, 1, 0)


def test_invalid_package_moves_to_failed(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_catalog(settings)
    package = write_package(settings)
    manifest_path = package / "annotation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["attributes"][0]["unit"] = "eV"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    preview = preview_annotation_package(package, settings)
    assert not preview.can_import

    with pytest.raises(AnnotationPackageError, match="moved"):
        import_annotation_package(package, preview.preview_token, settings)

    assert not package.exists()
    assert (settings.failed_annotations_directory / "rdkit-001").is_dir()

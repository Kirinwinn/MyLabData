"""Service tests against a temporary third-version DryData layout."""

import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from core.config import Settings
from schemas.catalog import PropertyUpdateRequest
from services.commands import DryDataCommands
from services.queries import DryDataQueries


def _create_v3_database(root: Path) -> None:
    root.mkdir(parents=True)
    database = duckdb.connect(str(root / "DryData.duckdb"))
    try:
        database.execute(
            """
            CREATE TABLE Molecules (
                molecule_id BIGINT, lab_id VARCHAR, canonical_smiles VARCHAR,
                channel VARCHAR, created_at TIMESTAMP
            );
            CREATE TABLE Attributes (
                attribute_id BIGINT, attribute_key VARCHAR, attribute_name VARCHAR,
                value_type VARCHAR, unit VARCHAR, description VARCHAR
            );
            CREATE TABLE Entries (
                entry_id BIGINT, attribute_id BIGINT, entry_key VARCHAR,
                annotation_kind VARCHAR, method_name VARCHAR, method_version VARCHAR,
                conditions_json JSON, is_mutable BOOLEAN, description VARCHAR
            );
            CREATE TABLE Annotations (
                molecule_id BIGINT, entry_id BIGINT, value_number DOUBLE,
                value_text VARCHAR, value_boolean BOOLEAN, created_at TIMESTAMP,
                updated_at TIMESTAMP
            );
            CREATE TABLE Sources (
                source_id BIGINT, source_key VARCHAR, source_type VARCHAR, description VARCHAR
            );
            CREATE TABLE Imports (
                import_id BIGINT, source_id BIGINT, file_hash VARCHAR, data_type VARCHAR,
                status VARCHAR, processor VARCHAR, total_rows BIGINT, error_message VARCHAR,
                created_at TIMESTAMP, finished_at TIMESTAMP
            );
            """
        )
    finally:
        database.close()


def test_v3_commands_import_molecules_and_update_property(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    incoming = root / "Incoming" / "Molecules"
    incoming.mkdir(parents=True)
    pq.write_table(
        pa.table({"canonical_smiles": pa.array(["CCO", "CCO", "", "CCN"], pa.string())}),
        incoming / "batch.parquet",
    )
    commands = DryDataCommands(Settings(data_root=root, memory_limit="1GB", threads=1))
    package_id = commands.packages.list_incoming()[0].package_id

    imported, archived = commands.import_package(package_id)

    assert archived is True
    assert imported.total_rows == 4
    assert imported.inserted_rows == 2
    assert imported.duplicate_rows == 1
    assert imported.invalid_rows == 1
    assert not (incoming / "batch.parquet").exists()
    assert (root / "Processed" / "Molecules" / "batch.parquet").is_file()

    database = duckdb.connect(str(root / "DryData.duckdb"))
    try:
        assert database.execute("SELECT count(*) FROM Molecules").fetchone() == (2,)
        database.execute(
            """
            INSERT INTO Attributes VALUES (1, 'purchased', 'Purchased', 'boolean', NULL, NULL);
            INSERT INTO Entries VALUES (
                1, 1, 'purchased.manual', 'property', 'Manual', NULL, '{}', true, NULL
            );
            """
        )
        molecule_id = database.execute("SELECT min(molecule_id) FROM Molecules").fetchone()[0]
    finally:
        database.close()

    updated = commands.update_property(
        molecule_id,
        1,
        PropertyUpdateRequest(value_boolean=True, source="manual:test"),
    )

    assert updated.created is True
    database = duckdb.connect(str(root / "DryData.duckdb"), read_only=True)
    try:
        assert database.execute(
            "SELECT value_boolean FROM Annotations WHERE molecule_id = ? AND entry_id = 1",
            [molecule_id],
        ).fetchone() == (True,)
    finally:
        database.close()


def test_v3_annotation_package_preview_uses_access_layer(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    database = duckdb.connect(str(root / "DryData.duckdb"))
    database.execute(
        """
        INSERT INTO Molecules VALUES (1, 'L00000001', 'CCO', NULL, CURRENT_TIMESTAMP);
        INSERT INTO Attributes VALUES (1, 'score', 'Score', 'number', NULL, NULL);
        INSERT INTO Entries VALUES
          (1, 1, 'score.test', 'calculation', 'Test', '1.0', '{}', false, NULL)
        """
    )
    database.close()
    package = root / "Incoming" / "Annotations" / "score-001"
    package.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "processor_name": "Test",
        "processor_version": "1.0",
        "attributes": [
            {
                "attribute_key": "score",
                "attribute_name": "Score",
                "value_type": "number",
                "unit": None,
                "description": None,
            }
        ],
        "entries": [
            {
                "entry_key": "score.test",
                "attribute_key": "score",
                "annotation_kind": "calculation",
                "method_name": "Test",
                "method_version": "1.0",
                "conditions": {},
                "source_key": None,
                "is_mutable": False,
                "description": None,
            }
        ],
        "data_files": ["annotations.parquet"],
        "generated_at": "2026-09-14T00:00:00+08:00",
    }
    report = {
        "status": "completed",
        "input_rows": 1,
        "output_annotations": 1,
        "rejected_rows": 0,
        "duplicate_rows": 0,
        "warnings": [],
        "started_at": "2026-09-14T00:00:00+08:00",
        "finished_at": "2026-09-14T00:01:00+08:00",
    }
    (package / "annotation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "processing_report.json").write_text(json.dumps(report), encoding="utf-8")
    pq.write_table(
        pa.table(
            {
                "canonical_smiles": pa.array(["CCO"], pa.string()),
                "attribute_key": pa.array(["score"], pa.string()),
                "entry_key": pa.array(["score.test"], pa.string()),
                "value_number": pa.array([0.5], pa.float64()),
                "value_text": pa.array([None], pa.string()),
                "value_boolean": pa.array([None], pa.bool_()),
            }
        ),
        package / "annotations.parquet",
    )

    queries = DryDataQueries(Settings(data_root=root, memory_limit="1GB", threads=1))
    package_id = queries.list_packages()[0].package_id
    preview = queries.preview_package(package_id)

    assert preview.can_import is True
    assert preview.expected_inserts == 1
    assert preview.attributes[0].status == "existing"
    assert preview.entries[0].status == "existing"

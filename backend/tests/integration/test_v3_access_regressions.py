"""Regression coverage migrated from the removed legacy database and services."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from access.database import DryDataDatabase, DryDataDatabaseError, DryDataSchemaError
from access.paths import DryDataPaths
from core.config import Settings
from schemas.catalog import PropertyUpdateRequest, SearchRequest
from services.commands import DryDataCommands
from services.queries import DryDataQueries


def _create_v3_database(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute(
            """
            CREATE TABLE Molecules (molecule_id BIGINT, lab_id VARCHAR,
              canonical_smiles VARCHAR, channel VARCHAR, created_at TIMESTAMP);
            CREATE TABLE Attributes (attribute_id BIGINT, attribute_key VARCHAR,
              attribute_name VARCHAR, value_type VARCHAR, unit VARCHAR,
              description VARCHAR);
            CREATE TABLE Entries (entry_id BIGINT, attribute_id BIGINT,
              entry_key VARCHAR, annotation_kind VARCHAR, method_name VARCHAR,
              method_version VARCHAR, conditions_json JSON, is_mutable BOOLEAN,
              description VARCHAR);
            CREATE TABLE Annotations (molecule_id BIGINT, entry_id BIGINT,
              value_number DOUBLE, value_text VARCHAR, value_boolean BOOLEAN,
              created_at TIMESTAMP, updated_at TIMESTAMP);
            CREATE TABLE Sources (source_id BIGINT, source_key VARCHAR,
              source_type VARCHAR, description VARCHAR);
            CREATE TABLE Imports (import_id BIGINT, source_id BIGINT,
              file_hash VARCHAR, data_type VARCHAR, status VARCHAR,
              processor VARCHAR, total_rows BIGINT, error_message VARCHAR,
              created_at TIMESTAMP, finished_at TIMESTAMP);
            """
        )


def _annotation_package(
    root: Path,
    *,
    name: str,
    attribute_unit: str | None = None,
    method_version: str = "1.0",
    value_number: float | None = 0.5,
    value_text: str | None = None,
) -> Path:
    package = root / "Incoming" / "Annotations" / name
    package.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "processor_name": "V3Regression",
        "processor_version": "1.0",
        "attributes": [
            {
                "attribute_key": "score",
                "attribute_name": "Score",
                "value_type": "number",
                "unit": attribute_unit,
                "description": None,
            }
        ],
        "entries": [
            {
                "entry_key": "score.test",
                "attribute_key": "score",
                "annotation_kind": "calculation",
                "method_name": "Test",
                "method_version": method_version,
                "conditions": {},
                "source_key": None,
                "is_mutable": False,
                "description": None,
            }
        ],
        "data_files": ["annotations.parquet"],
        "generated_at": "2026-09-15T00:00:00+08:00",
    }
    report = {
        "status": "completed",
        "input_rows": 1,
        "output_annotations": 1,
        "rejected_rows": 0,
        "duplicate_rows": 0,
        "warnings": [],
        "started_at": "2026-09-15T00:00:00+08:00",
        "finished_at": "2026-09-15T00:01:00+08:00",
    }
    (package / "annotation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "processing_report.json").write_text(json.dumps(report), encoding="utf-8")
    pq.write_table(
        pa.table(
            {
                "canonical_smiles": pa.array(["CCO"], pa.string()),
                "attribute_key": pa.array(["score"], pa.string()),
                "entry_key": pa.array(["score.test"], pa.string()),
                "value_number": pa.array([value_number], pa.float64()),
                "value_text": pa.array([value_text], pa.string()),
                "value_boolean": pa.array([None], pa.bool_()),
            }
        ),
        package / "annotations.parquet",
    )
    return package


def test_v3_database_requires_file_schema_and_rolls_back(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    access = DryDataDatabase(DryDataPaths(root))
    with pytest.raises(DryDataDatabaseError, match="does not exist"):
        with access.connection():
            pass

    root.mkdir()
    duckdb.connect(str(root / "DryData.duckdb")).close()
    with pytest.raises(DryDataSchemaError, match="Molecules"):
        access.verify_v3_schema()

    (root / "DryData.duckdb").unlink()
    _create_v3_database(root)
    access.verify_v3_schema()
    with pytest.raises(RuntimeError, match="force rollback"):
        with access.transaction() as connection:
            connection.execute(
                "INSERT INTO Molecules VALUES (1, 'L1', 'CCO', NULL, CURRENT_TIMESTAMP)"
            )
            raise RuntimeError("force rollback")
    with access.connection() as connection:
        assert connection.execute("SELECT count(*) FROM Molecules").fetchone() == (0,)


def test_v3_molecule_preview_preserves_legacy_edge_counts(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute("INSERT INTO Molecules VALUES (1, 'L1', 'CCO', NULL, CURRENT_TIMESTAMP)")
    incoming = root / "Incoming" / "Molecules"
    incoming.mkdir(parents=True)
    pq.write_table(
        pa.table({"canonical_smiles": pa.array(["CCO", "CCN", "CCN", "", None], pa.string())}),
        incoming / "edge.parquet",
    )
    queries = DryDataQueries(Settings(data_root=root, memory_limit="1GB", threads=1))
    package_id = queries.list_packages()[0].package_id

    preview = queries.preview_package(package_id)

    assert preview == {
        "package_name": "edge.parquet",
        "package_hash": preview["package_hash"],
        "total_rows": 5,
        "valid_rows": 3,
        "new_rows": 1,
        "existing_rows": 1,
        "duplicate_rows": 1,
        "invalid_rows": 2,
    }


def test_v3_search_keeps_and_or_and_type_validation(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute(
            """
            INSERT INTO Molecules VALUES
              (1, 'L1', 'C1', NULL, CURRENT_TIMESTAMP),
              (2, 'L2', 'C2', NULL, CURRENT_TIMESTAMP),
              (3, 'L3', 'C3', NULL, CURRENT_TIMESTAMP);
            INSERT INTO Attributes VALUES
              (1, 'score', 'Score', 'number', NULL, NULL),
              (2, 'active', 'Active', 'boolean', NULL, NULL);
            INSERT INTO Entries VALUES
              (1, 1, 'score.test', 'calculation', 'Test', NULL, '{}', false, NULL),
              (2, 2, 'active.test', 'calculation', 'Test', NULL, '{}', false, NULL);
            INSERT INTO Annotations VALUES
              (1, 1, 50, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (2, 1, 50, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (3, 1, 90, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (1, 2, NULL, NULL, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (2, 2, NULL, NULL, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (3, 2, NULL, NULL, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    queries = DryDataQueries(Settings(data_root=root, memory_limit="1GB", threads=1))
    conditions = [
        {
            "attribute_key": "score",
            "entry_key": "score.test",
            "operator": "between",
            "value": 40,
            "second_value": 60,
        },
        {
            "attribute_key": "active",
            "entry_key": "active.test",
            "operator": "eq",
            "value": True,
        },
    ]
    both = queries.search(SearchRequest(conditions=conditions, logic="and"))
    either = queries.search(SearchRequest(conditions=conditions, logic="or"))

    assert [item.molecule_id for item in both.molecules] == [1]
    assert [item.molecule_id for item in either.molecules] == [1, 2, 3]
    with pytest.raises(ValueError, match="invalid for number"):
        queries.search(
            SearchRequest(
                conditions=[
                    {
                        "attribute_key": "score",
                        "entry_key": "score.test",
                        "operator": "contains",
                        "value": "5",
                    }
                ]
            )
        )


def test_v3_annotation_preview_reports_conflicts_and_value_errors(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute(
            """
            INSERT INTO Molecules VALUES (1, 'L1', 'CCO', NULL, CURRENT_TIMESTAMP);
            INSERT INTO Attributes VALUES (1, 'score', 'Score', 'number', 'nm', NULL);
            INSERT INTO Entries VALUES
              (1, 1, 'score.test', 'calculation', 'Test', '1.0', '{}', false, NULL)
            """
        )
    _annotation_package(root, name="conflict", attribute_unit="eV", method_version="2.0")
    queries = DryDataQueries(Settings(data_root=root, memory_limit="1GB", threads=1))
    conflict = queries.preview_package(queries.list_packages()[0].package_id)

    assert conflict.can_import is False
    assert conflict.attributes[0].conflicts == ["unit"]
    assert conflict.entries[0].conflicts == ["method_version"]

    package = root / "Incoming" / "Annotations" / "conflict"
    for item in package.iterdir():
        item.unlink()
    package.rmdir()
    _annotation_package(root, name="wrong-value", value_number=None, value_text="wrong")
    invalid = queries.preview_package(queries.list_packages()[0].package_id)
    assert invalid.can_import is False
    assert any("invalid rows" in error for error in invalid.errors)


def test_v3_changed_preview_token_and_immutable_entry_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    with duckdb.connect(str(root / "DryData.duckdb")) as database:
        database.execute(
            """
            INSERT INTO Molecules VALUES (1, 'L1', 'CCO', NULL, CURRENT_TIMESTAMP);
            INSERT INTO Attributes VALUES (1, 'score', 'Score', 'number', NULL, NULL);
            INSERT INTO Entries VALUES
              (1, 1, 'score.test', 'calculation', 'Test', '1.0', '{}', false, NULL)
            """
        )
    package = _annotation_package(root, name="token")
    settings = Settings(data_root=root, memory_limit="1GB", threads=1)
    queries = DryDataQueries(settings)
    package_id = queries.list_packages()[0].package_id
    preview = queries.preview_package(package_id)
    report = json.loads((package / "processing_report.json").read_text(encoding="utf-8"))
    report["warnings"] = ["changed"]
    (package / "processing_report.json").write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid or the package changed"):
        DryDataCommands(settings).import_package(
            package_id,
            preview_token=preview.preview_token,
        )
    with pytest.raises(ValueError, match="mutable Property"):
        DryDataCommands(settings).update_property(
            1,
            1,
            PropertyUpdateRequest(value_number=2.0, source="test"),
        )

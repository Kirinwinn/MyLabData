"""End-to-end temporary-runtime checks for the finalized DryData layout."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import monotonic, sleep

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from access.packages import PackageStore
from access.paths import DryDataPathError, DryDataPaths
from core.config import Settings
from main import create_app


def _create_v3_database(root: Path) -> None:
    root.mkdir(parents=True)
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


def _wait(client: TestClient, job_id: str, timeout: float = 10) -> dict:
    deadline = monotonic() + timeout
    stable = {"completed", "failed", "cancelled", "waiting_confirmation", "archive_pending"}
    while monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in stable:
            return job
        sleep(0.02)
    raise AssertionError(f"Job did not reach a stable state: {job_id}")


def _submit_and_wait(client: TestClient, url: str, payload: dict | None = None) -> dict:
    response = client.post(url, json=payload) if payload is not None else client.post(url)
    assert response.status_code == 202
    return _wait(client, response.json()["job_id"])


def _write_annotation_package(root: Path) -> Path:
    package = root / "Incoming" / "Annotations" / "score-001"
    package.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "processor_name": "RuntimeFlowTest",
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
                "entry_key": "score.runtime_test",
                "attribute_key": "score",
                "annotation_kind": "calculation",
                "method_name": "RuntimeFlowTest",
                "method_version": "1.0",
                "conditions": {},
                "source_key": None,
                "is_mutable": False,
                "description": None,
            }
        ],
        "data_files": ["annotations.parquet"],
        "generated_at": "2026-09-14T12:00:00+08:00",
    }
    report = {
        "status": "completed",
        "input_rows": 2,
        "output_annotations": 2,
        "rejected_rows": 0,
        "duplicate_rows": 0,
        "warnings": [],
        "started_at": "2026-09-14T12:00:00+08:00",
        "finished_at": "2026-09-14T12:01:00+08:00",
    }
    (package / "annotation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "processing_report.json").write_text(json.dumps(report), encoding="utf-8")
    pq.write_table(
        pa.table(
            {
                "canonical_smiles": pa.array(["CCO", "CCN"], pa.string()),
                "attribute_key": pa.array(["score", "score"], pa.string()),
                "entry_key": pa.array(["score.runtime_test", "score.runtime_test"], pa.string()),
                "value_number": pa.array([0.4, 0.8], pa.float64()),
                "value_text": pa.array([None, None], pa.string()),
                "value_boolean": pa.array([None, None], pa.bool_()),
            }
        ),
        package / "annotations.parquet",
    )
    return package


def _business_counts(root: Path) -> tuple[int, ...]:
    with duckdb.connect(str(root / "DryData.duckdb"), read_only=True) as database:
        return database.execute(
            """
            SELECT (SELECT count(*) FROM Molecules),
                   (SELECT count(*) FROM Attributes),
                   (SELECT count(*) FROM Entries),
                   (SELECT count(*) FROM Annotations),
                   (SELECT count(*) FROM Imports)
            """
        ).fetchone()


def test_complete_molecule_and_annotation_job_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    paths = DryDataPaths(root)
    paths.ensure_runtime_directories()
    molecule_file = paths.package_directory("incoming", "molecules") / "batch.parquet"
    pq.write_table(
        pa.table({"canonical_smiles": pa.array(["CCO", "CCN"], pa.string())}),
        molecule_file,
    )
    settings = Settings(data_root=root, memory_limit="1GB", threads=1)

    with TestClient(create_app(settings)) as client:
        package_job = _submit_and_wait(client, "/api/v1/packages/query")
        molecule = next(
            item for item in package_job["result"]["items"] if item["package_kind"] == "molecules"
        )
        before_preview = _business_counts(root)
        preview = _submit_and_wait(client, f"/api/v1/packages/{molecule['package_id']}/preview")
        assert preview["status"] == "completed"
        assert preview["result"]["new_rows"] == 2
        assert _business_counts(root) == before_preview

        imported = _submit_and_wait(client, f"/api/v1/packages/{molecule['package_id']}/imports")
        assert imported["status"] == "completed"
        assert imported["result"]["inserted_rows"] == 2
        assert not molecule_file.exists()
        assert (paths.package_directory("processed", "molecules") / molecule_file.name).is_file()

        annotation_package = _write_annotation_package(root)
        package_job = _submit_and_wait(client, "/api/v1/packages/query")
        annotation = next(
            item for item in package_job["result"]["items"] if item["package_kind"] == "annotations"
        )
        before_preview = _business_counts(root)
        preview = _submit_and_wait(client, f"/api/v1/packages/{annotation['package_id']}/preview")
        assert preview["status"] == "waiting_confirmation"
        assert preview["result"]["expected_inserts"] == 2
        assert _business_counts(root) == before_preview

        imported = _submit_and_wait(
            client,
            f"/api/v1/packages/{annotation['package_id']}/imports",
            {"preview_token": preview["result"]["preview_token"]},
        )
        assert imported["status"] == "completed"
        assert imported["result"]["inserted_rows"] == 2
        assert not annotation_package.exists()
        assert (
            paths.package_directory("processed", "annotations") / annotation_package.name
        ).is_dir()

    assert _business_counts(root) == (2, 1, 1, 2, 2)
    assert paths.jobs_database_path.is_file()
    assert all(directory.is_dir() for directory in paths.runtime_directories())


def test_failed_preview_stays_in_incoming_and_archives_never_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    _create_v3_database(root)
    paths = DryDataPaths(root)
    paths.ensure_runtime_directories()
    incoming = paths.package_directory("incoming", "molecules")
    invalid = incoming / "invalid.parquet"
    pq.write_table(pa.table({"wrong_column": ["CCO"]}), invalid)
    collision = incoming / "collision.parquet"
    pq.write_table(pa.table({"canonical_smiles": ["CCC"]}), collision)
    archived = paths.package_directory("processed", "molecules") / collision.name
    archived.write_bytes(b"existing archive must remain unchanged")

    with TestClient(create_app(Settings(data_root=root, memory_limit="1GB", threads=1))) as client:
        packages = _submit_and_wait(client, "/api/v1/packages/query")["result"]["items"]
        invalid_id = next(
            item["package_id"] for item in packages if item["package_name"] == invalid.name
        )
        collision_id = next(
            item["package_id"] for item in packages if item["package_name"] == collision.name
        )
        failed = _submit_and_wait(client, f"/api/v1/packages/{invalid_id}/preview")
        assert failed["status"] == "failed"
        assert invalid.is_file()
        assert not (paths.package_directory("failed", "molecules") / invalid.name).exists()

        pending = _submit_and_wait(client, f"/api/v1/packages/{collision_id}/imports")
        assert pending["status"] == "archive_pending"
        assert collision.is_file()
        assert archived.read_bytes() == b"existing archive must remain unchanged"


def test_path_boundary_and_symlink_packages_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "DryData"
    paths = DryDataPaths(root)
    paths.ensure_runtime_directories()
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"outside")

    with pytest.raises(DryDataPathError, match="inside"):
        paths.require_within_root(outside, must_exist=True)
    with pytest.raises(KeyError):
        PackageStore(paths).descriptor("../../outside.parquet")

    link = paths.package_directory("incoming", "molecules") / "linked.parquet"
    try:
        os.symlink(outside, link)
    except OSError:
        return
    assert PackageStore(paths).list_incoming() == []

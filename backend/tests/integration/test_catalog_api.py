"""API tests for catalog operations submitted as Query or Command Jobs."""

import zipfile
from pathlib import Path
from time import monotonic, sleep

import duckdb
from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app


def _create_v3_database(root: Path) -> duckdb.DuckDBPyConnection:
    root.mkdir(parents=True)
    connection = duckdb.connect(str(root / "DryData.duckdb"))
    connection.execute(
        """
        CREATE TABLE Molecules (molecule_id BIGINT, lab_id VARCHAR, canonical_smiles VARCHAR,
          channel VARCHAR, created_at TIMESTAMP);
        CREATE TABLE Attributes (attribute_id BIGINT, attribute_key VARCHAR,
          attribute_name VARCHAR, value_type VARCHAR, unit VARCHAR, description VARCHAR);
        CREATE TABLE Entries (entry_id BIGINT, attribute_id BIGINT, entry_key VARCHAR,
          annotation_kind VARCHAR, method_name VARCHAR, method_version VARCHAR,
          conditions_json JSON, is_mutable BOOLEAN, description VARCHAR);
        CREATE TABLE Annotations (molecule_id BIGINT, entry_id BIGINT, value_number DOUBLE,
          value_text VARCHAR, value_boolean BOOLEAN, created_at TIMESTAMP, updated_at TIMESTAMP);
        CREATE TABLE Sources (source_id BIGINT, source_key VARCHAR, source_type VARCHAR,
          description VARCHAR);
        CREATE TABLE Imports (import_id BIGINT, source_id BIGINT, file_hash VARCHAR,
          data_type VARCHAR, status VARCHAR, processor VARCHAR, total_rows BIGINT,
          error_message VARCHAR, created_at TIMESTAMP, finished_at TIMESTAMP);
        """
    )
    return connection


def _wait_for_job(client: TestClient, job_id: str, *, timeout: float = 5) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        sleep(0.02)
    raise AssertionError(f"Job {job_id} did not finish")


def test_catalog_operations_return_query_jobs(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    database_connection = _create_v3_database(settings.data_root)
    try:
        database_connection.execute(
            "INSERT INTO Molecules VALUES (1, 'L00000001', 'CCO', NULL, CURRENT_TIMESTAMP)"
        )
        database_connection.execute(
            """
            INSERT INTO Attributes VALUES
              (1, 'purchased', 'Purchased', 'boolean', NULL, NULL)
            """
        )
        database_connection.execute(
            """
            INSERT INTO Entries VALUES
              (1, 1, 'purchased.manual', 'property', 'Manual', NULL, '{}', true, NULL)
            """
        )
        database_connection.execute(
            """
            INSERT INTO Annotations VALUES
              (1, 1, NULL, NULL, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
            INSERT INTO Imports VALUES
              (1, NULL, 'abc123', 'annotations', 'completed', 'test.processor', 1,
               NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    finally:
        database_connection.close()

    with TestClient(create_app(settings)) as client:
        submitted = client.post("/api/v1/molecules/query", json={})
        assert submitted.status_code == 202
        molecules_job = _wait_for_job(client, submitted.json()["job_id"])
        assert molecules_job["job_kind"] == "query"
        assert molecules_job["result"]["items"][0]["canonical_smiles"] == "CCO"
        molecule_id = molecules_job["result"]["items"][0]["molecule_id"]

        detail_job = _wait_for_job(
            client,
            client.post(f"/api/v1/molecules/{molecule_id}/query").json()["job_id"],
        )
        assert detail_job["result"]["molecule_id"] == molecule_id
        assert "annotations" not in detail_job["result"]

        structure_job = _wait_for_job(
            client,
            client.post(f"/api/v1/molecules/{molecule_id}/structure-3d/query").json()["job_id"],
        )
        assert structure_job["job_kind"] == "query"
        assert structure_job["result"]["molecule_id"] == molecule_id
        assert "V2000" in structure_job["result"]["mol_block"]

        molecule_attributes_job = _wait_for_job(
            client,
            client.post(f"/api/v1/molecules/{molecule_id}/attributes/query").json()["job_id"],
        )
        molecule_attribute_id = molecule_attributes_job["result"]["items"][0]["attribute_id"]
        assert molecule_attribute_id == 1

        molecule_annotations_job = _wait_for_job(
            client,
            client.post(
                f"/api/v1/molecules/{molecule_id}/attributes/{molecule_attribute_id}/annotations/query"
            ).json()["job_id"],
        )
        assert molecule_annotations_job["result"]["items"][0]["value"] is True
        assert molecule_annotations_job["result"]["items"][0]["entry_key"] == "purchased.manual"

        attributes_job = _wait_for_job(
            client,
            client.post("/api/v1/attributes/query").json()["job_id"],
        )
        attribute_id = attributes_job["result"]["items"][0]["attribute_id"]
        entries_job = _wait_for_job(
            client,
            client.post(f"/api/v1/attributes/{attribute_id}/entries/query").json()["job_id"],
        )
        assert entries_job["result"]["items"][0]["entry_key"] == "purchased.manual"
        assert "source_id" not in entries_job["result"]["items"][0]

        attribute_stats_job = _wait_for_job(
            client,
            client.post(f"/api/v1/attributes/{attribute_id}/stats/query").json()["job_id"],
        )
        assert attribute_stats_job["result"]["items"][0]["true_count"] == 1

        preheat_job = _wait_for_job(
            client,
            client.post("/api/v1/attributes/stats/preheat").json()["job_id"],
        )
        assert preheat_job["result"]["total"] == 1
        assert preheat_job["result"]["preheated"] == 1
        assert preheat_job["result"]["failed"] == 0
        assert preheat_job["result"]["elapsed_seconds"] >= 0
        cached = list((settings.data_root / "Cache").glob("entry-statistics-*.json"))
        assert len(cached) == 1

        search_job = _wait_for_job(
            client,
            client.post(
                "/api/v1/search",
                json={
                    "conditions": [
                        {
                            "attribute_key": "purchased",
                            "entry_key": "purchased.manual",
                            "operator": "eq",
                            "value": True,
                        }
                    ]
                },
            ).json()["job_id"],
        )
        assert search_job["result"]["molecules"][0]["molecule_id"] == molecule_id

        stats_job = _wait_for_job(client, client.post("/api/v1/stats/query").json()["job_id"])
        assert stats_job["result"]["molecules"] == 1
        imports_job = _wait_for_job(
            client,
            client.post("/api/v1/imports/query", json={}).json()["job_id"],
        )
        assert imports_job["result"]["items"][0]["processor"] == "test.processor"
        import_job = _wait_for_job(
            client,
            client.post("/api/v1/imports/1/query").json()["job_id"],
        )
        assert import_job["result"]["file_hash"] == "abc123"


def test_smiles_export_builds_chunked_zip(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    database_connection = _create_v3_database(settings.data_root)
    try:
        for index in range(1, 6):
            database_connection.execute(
                "INSERT INTO Molecules VALUES (?, ?, ?, NULL, CURRENT_TIMESTAMP)",
                [index, f"L{index:08d}", f"C{'C' * index}O"],
            )
    finally:
        database_connection.close()

    with TestClient(create_app(settings)) as client:
        rejected = client.post("/api/v1/molecules/smiles/export", json={"rows_per_file": 0})
        assert rejected.status_code == 422

        submitted = client.post("/api/v1/molecules/smiles/export", json={"rows_per_file": 2})
        assert submitted.status_code == 202
        job = _wait_for_job(client, submitted.json()["job_id"])
        assert job["status"] == "completed"
        assert job["result"]["total"] == 5
        assert job["result"]["rows_per_file"] == 2
        assert job["result"]["files"] == [
            "smiles_0001.csv",
            "smiles_0002.csv",
            "smiles_0003.csv",
        ]

        archive_path = settings.data_root / "Temp" / "exports" / job["result"]["file_name"]
        with zipfile.ZipFile(archive_path) as archive:
            first = archive.read("smiles_0001.csv").decode("utf-8").splitlines()
            assert first[0] == "SMILES"
            assert len(first) == 3
            third = archive.read("smiles_0003.csv").decode("utf-8").splitlines()
            assert third == ["SMILES", "CCCCCCO"]

        downloaded = client.get(f"/api/v1/jobs/{job['job_id']}/export")
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("application/zip")


def test_entry_result_filter_for_molecules_and_export(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    database_connection = _create_v3_database(settings.data_root)
    try:
        database_connection.execute(
            """
            INSERT INTO Attributes VALUES
              (1, 'absorption_wavelength', 'Absorption Wavelength', 'number', 'nm', NULL)
            """
        )
        database_connection.execute(
            """
            INSERT INTO Entries VALUES
              (1, 1, 'absorption_wavelength.flame.CS(C)=O', 'prediction', 'Flame', '1.0',
               '{}', FALSE, NULL)
            """
        )
        database_connection.execute(
            """
            INSERT INTO Molecules VALUES
              (1, 'L00000001', 'CCO', NULL, CURRENT_TIMESTAMP),
              (2, 'L00000002', 'CCC', NULL, CURRENT_TIMESTAMP),
              (3, 'L00000003', 'CCN', NULL, CURRENT_TIMESTAMP)
            """
        )
        database_connection.execute(
            """
            INSERT INTO Annotations VALUES
              (1, 1, 700, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (3, 1, 750, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    finally:
        database_connection.close()

    with TestClient(create_app(settings)) as client:
        index_job = _wait_for_job(
            client, client.post("/api/v1/entries/index/query").json()["job_id"]
        )
        assert index_job["result"]["items"] == [
            {
                "entry_id": 1,
                "entry_key": "absorption_wavelength.flame.CS(C)=O",
                "attribute_key": "absorption_wavelength",
                "attribute_name": "Absorption Wavelength",
                "annotation_kind": "prediction",
                "method_name": "Flame",
                "method_version": "1.0",
                "conditions": {},
                "is_mutable": False,
                "description": None,
            }
        ]

        missing_job = _wait_for_job(
            client,
            client.post(
                "/api/v1/molecules/query",
                json={"entry_filter": {"entry_id": 1, "has_results": False}},
            ).json()["job_id"],
        )
        assert missing_job["result"]["total"] == 1
        assert missing_job["result"]["items"][0]["molecule_id"] == 2

        has_job = _wait_for_job(
            client,
            client.post(
                "/api/v1/molecules/query",
                json={"entry_filter": {"entry_id": 1, "has_results": True}},
            ).json()["job_id"],
        )
        assert has_job["result"]["total"] == 2
        assert [item["molecule_id"] for item in has_job["result"]["items"]] == [1, 3]

        export_job = _wait_for_job(
            client,
            client.post(
                "/api/v1/molecules/smiles/export",
                json={
                    "rows_per_file": 10,
                    "entry_filter": {"entry_id": 1, "has_results": False},
                },
            ).json()["job_id"],
        )
        assert export_job["result"]["total"] == 1
        archive_path = (
            settings.data_root / "Temp" / "exports" / export_job["result"]["file_name"]
        )
        with zipfile.ZipFile(archive_path) as archive:
            content = archive.read("smiles_0001.csv").decode("utf-8").splitlines()
            assert content == ["SMILES", "CCC"]


def test_search_and_property_update_are_submitted_as_jobs(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    _create_v3_database(settings.data_root).close()
    with TestClient(create_app(settings)) as client:
        search = client.post(
            "/api/v1/search",
            json={
                "conditions": [
                    {
                        "attribute_id": 1,
                        "entry_id": 1,
                        "operator": "eq",
                        "value": True,
                    }
                ],
            },
        )
        assert search.status_code == 202
        failed_search = _wait_for_job(client, search.json()["job_id"])
        assert failed_search["job_kind"] == "query"
        assert failed_search["status"] == "failed"

        update = client.put(
            "/api/v1/molecules/1/properties/1",
            json={"value_boolean": True, "source": "manual:test"},
        )
        assert update.status_code == 202
        assert client.get(f"/api/v1/jobs/{update.json()['job_id']}").json()["job_kind"] == "command"

"""HTTP tests for Package-ID based Job submission."""

from pathlib import Path
from time import monotonic, sleep

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app


def _wait_for_job(client: TestClient, job_id: str, *, timeout: float = 5) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled", "waiting_confirmation"}:
            return job
        sleep(0.02)
    raise AssertionError(f"Job {job_id} did not finish")


def test_package_operations_return_jobs_without_accepting_paths(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    settings.data_root.mkdir(parents=True)
    database = duckdb.connect(str(settings.data_root / "DryData.duckdb"))
    database.execute(
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
    database.close()
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True)
    pq.write_table(
        pa.table({"canonical_smiles": pa.array(["CCO"], pa.string())}),
        incoming / "molecules.parquet",
    )
    application = create_app(settings)

    with TestClient(application) as client:
        packages_response = client.post("/api/v1/packages/query")
        assert packages_response.status_code == 202
        packages_job = _wait_for_job(client, packages_response.json()["job_id"])
        assert packages_job["job_kind"] == "query"
        package = packages_job["result"]["items"][0]
        assert "path" not in package
        package_id = package["package_id"]

        detail_job = _wait_for_job(
            client,
            client.post(f"/api/v1/packages/{package_id}/query").json()["job_id"],
        )
        assert detail_job["result"]["files"] == ["molecules.parquet"]
        assert "path" not in detail_job["result"]

        preview = client.post(f"/api/v1/packages/{package_id}/preview")
        assert preview.status_code == 202
        preview_job = _wait_for_job(client, preview.json()["job_id"])
        assert preview_job["job_kind"] == "query"
        assert preview_job["status"] == "waiting_confirmation"
        assert preview_job["result"]["new_rows"] == 1
        assert "file_path" not in preview_job["result"]

        # Preview is read-only. Import must carry the hash that was reviewed.
        database = duckdb.connect(str(settings.data_root / "DryData.duckdb"), read_only=True)
        try:
            assert database.execute("SELECT count(*) FROM Molecules").fetchone() == (0,)
        finally:
            database.close()
        unconfirmed = client.post(f"/api/v1/packages/{package_id}/imports")
        unconfirmed_job = _wait_for_job(client, unconfirmed.json()["job_id"])
        assert unconfirmed_job["status"] == "failed"
        assert "preview hash" in unconfirmed_job["error_message"]
        confirmed = client.post(
            f"/api/v1/packages/{package_id}/imports",
            json={"preview_hash": preview_job["result"]["package_hash"]},
        )
        assert confirmed.status_code == 202
        imported = _wait_for_job(client, confirmed.json()["job_id"])
        assert imported["status"] == "completed"
        assert imported["result"]["inserted_rows"] == 1
        assert imported["result"]["archived"] is True
        assert not (incoming / "molecules.parquet").exists()
        assert (settings.data_root / "Processed" / "Molecules" / "molecules.parquet").is_file()
        database = duckdb.connect(str(settings.data_root / "DryData.duckdb"), read_only=True)
        try:
            assert database.execute("SELECT canonical_smiles FROM Molecules").fetchall() == [
                ("CCO",)
            ]
        finally:
            database.close()

        missing_preview = client.post("/api/v1/packages/not-a-package/preview")
        assert missing_preview.status_code == 202
        missing_job = _wait_for_job(client, missing_preview.json()["job_id"])
        assert missing_job["status"] == "failed"

        assert (
            client.post(
                "/api/v1/jobs",
                json={"job_type": "package_import", "payload": {"file_path": "C:\\secret"}},
            ).status_code
            == 405
        )

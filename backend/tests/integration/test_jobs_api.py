"""HTTP tests for Package-ID based asynchronous submission."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from mylabdata.core.config import Settings
from mylabdata.main import create_app


def test_package_preview_returns_job_id_without_accepting_paths(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    incoming = settings.incoming_molecules_directory
    incoming.mkdir(parents=True)
    pq.write_table(
        pa.table({"canonical_smiles": pa.array(["CCO"], pa.string())}),
        incoming / "molecules.parquet",
    )
    application = create_app(settings)

    with TestClient(application) as client:
        packages = client.get("/api/v1/packages").json()
        assert len(packages) == 1
        assert "path" not in packages[0]
        package_id = packages[0]["package_id"]

        response = client.post(f"/api/v1/packages/{package_id}/preview")
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] in {
            "queued",
            "validating",
            "completed",
        }

        assert client.post(
            "/api/v1/jobs",
            json={"job_type": "molecule_import", "payload": {"file_path": "C:\\secret"}},
        ).status_code == 405
        assert client.post("/api/v1/packages/not-a-package/preview").status_code == 404

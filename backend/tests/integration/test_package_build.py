"""Integration tests for building Annotation Packages from uploaded source files."""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic, sleep

import duckdb
from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app

CSV_CONTENT = b"SMILES,Abs_pred\nCCO,311.5\nCCC,\nCCN,400\n"


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
        database.execute(
            """
            INSERT INTO Attributes VALUES
              (1, 'absorption_wavelength', 'Absorption Wavelength', 'number', 'nm',
               '分子紫外最强吸收波长')
            """
        )
        database.execute(
            """
            INSERT INTO Entries VALUES
              (1, 1, 'absorption_wavelength.deepmpp.CS(C)=O', 'prediction', 'DeepMPP',
               NULL, '{"solvent_smiles": "CS(C)=O"}', FALSE,
               'DeepMPP 在 CS(C)=O 条件下预测的 Absorption Wavelength。')
            """
        )
        database.execute(
            """
            INSERT INTO Molecules VALUES
              (1, 'L00000001', 'CCO', NULL, CURRENT_TIMESTAMP),
              (2, 'L00000002', 'CCC', NULL, CURRENT_TIMESTAMP)
            """
        )


def _wait_for_job(client: TestClient, job_id: str, *, timeout: float = 10) -> dict:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled", "waiting_confirmation"}:
            return job
        sleep(0.02)
    raise AssertionError(f"Job {job_id} did not finish")


def _existing_build_request(*, dry_run: bool, package_name: str = "deepmpp_gapfill_v1") -> dict:
    return {
        "package_name": package_name,
        "source_file": "results.csv",
        "identifier_column_index": 0,
        "processor_name": "DeepMPP processor",
        "processor_version": "1.0",
        "mappings": [
            {
                "column_index": 1,
                "column_name": "Abs_pred",
                "attribute": {"mode": "existing", "attribute_key": "absorption_wavelength"},
                "entry": {
                    "mode": "existing",
                    "entry_key": "absorption_wavelength.deepmpp.CS(C)=O",
                },
            }
        ],
        "dry_run": dry_run,
    }


def test_source_file_endpoints_and_guards(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    _create_v3_database(settings.data_root)

    with TestClient(create_app(settings)) as client:
        uploaded = client.post(
            "/api/v1/source-files",
            files={"file": ("results.csv", CSV_CONTENT, "text/csv")},
        )
        assert uploaded.status_code == 201
        profile = uploaded.json()
        assert profile["name"] == "results.csv"
        assert profile["total_rows"] == 3
        assert [(column["name"], column["value_type"]) for column in profile["columns"]] == [
            ("SMILES", "text"),
            ("Abs_pred", "number"),
        ]
        assert profile["preview_rows"][0] == ["CCO", "311.5"]
        assert (settings.data_root / "New" / "results.csv").is_file()

        duplicate = client.post(
            "/api/v1/source-files",
            files={"file": ("results.csv", CSV_CONTENT, "text/csv")},
        )
        assert duplicate.status_code == 409

        unsafe = client.post(
            "/api/v1/source-files",
            files={"file": ("../escape.csv", CSV_CONTENT, "text/csv")},
        )
        assert unsafe.status_code == 400

        assert [item["name"] for item in client.get("/api/v1/source-files").json()] == [
            "results.csv"
        ]
        reprofile = client.get("/api/v1/source-files/results.csv/profile")
        assert reprofile.status_code == 200
        assert reprofile.json()["columns"][1]["filled_rows"] == 2

        assert client.get("/api/v1/source-files/missing.csv/profile").status_code == 404

        assert client.delete("/api/v1/source-files/results.csv").status_code == 204
        assert client.get("/api/v1/source-files").json() == []
        assert client.delete("/api/v1/source-files/results.csv").status_code == 404


def test_build_reuses_registered_definitions_without_conflicts(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    _create_v3_database(settings.data_root)
    package = settings.data_root / "Incoming" / "Annotations" / "deepmpp_gapfill_v1"

    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/source-files",
            files={"file": ("results.csv", CSV_CONTENT, "text/csv")},
        )

        preview = _wait_for_job(
            client,
            client.post(
                "/api/v1/packages/build", json=_existing_build_request(dry_run=True)
            ).json()["job_id"],
        )
        assert preview["status"] == "completed"
        result = preview["result"]
        assert result["dry_run"] is True
        assert (result["attributes_existing"], result["attributes_new"]) == (1, 0)
        assert (result["entries_existing"], result["entries_new"]) == (1, 0)
        assert result["annotation_rows"] == 2
        assert (result["linkable_molecules"], result["unlinkable_molecules"]) == (1, 1)
        assert result["already_in_database"] == 0
        assert result["expected_inserts"] == 1
        assert result["rejected_rows"] == 1
        assert not package.exists()

        built = _wait_for_job(
            client,
            client.post(
                "/api/v1/packages/build", json=_existing_build_request(dry_run=False)
            ).json()["job_id"],
        )
        assert built["status"] == "completed"
        assert built["result"]["dry_run"] is False
        assert sorted(item.name for item in package.iterdir()) == [
            "annotation_manifest.json",
            "annotations.parquet",
            "processing_report.json",
        ]

        manifest = json.loads((package / "annotation_manifest.json").read_text(encoding="utf-8"))
        assert manifest["attributes"] == [
            {
                "attribute_key": "absorption_wavelength",
                "attribute_name": "Absorption Wavelength",
                "value_type": "number",
                "unit": "nm",
                "description": "分子紫外最强吸收波长",
            }
        ]
        assert manifest["entries"] == [
            {
                "entry_key": "absorption_wavelength.deepmpp.CS(C)=O",
                "attribute_key": "absorption_wavelength",
                "annotation_kind": "prediction",
                "method_name": "DeepMPP",
                "method_version": None,
                "conditions": {"solvent_smiles": "CS(C)=O"},
                "is_mutable": False,
                "description": "DeepMPP 在 CS(C)=O 条件下预测的 Absorption Wavelength。",
            }
        ]
        report = json.loads((package / "processing_report.json").read_text(encoding="utf-8"))
        assert report["output_annotations"] == 2
        assert report["rejected_rows"] == 0

        listed = _wait_for_job(client, client.post("/api/v1/packages/query").json()["job_id"])
        package_id = next(
            item["package_id"]
            for item in listed["result"]["items"]
            if item["package_name"] == "deepmpp_gapfill_v1"
        )
        package_preview = _wait_for_job(
            client, client.post(f"/api/v1/packages/{package_id}/preview").json()["job_id"]
        )
        assert package_preview["status"] == "waiting_confirmation"
        preview_result = package_preview["result"]
        assert preview_result["can_import"] is True
        assert preview_result["errors"] == []
        assert [(item["status"], item["conflicts"]) for item in preview_result["attributes"]] == [
            ("existing", [])
        ]
        assert [(item["status"], item["conflicts"]) for item in preview_result["entries"]] == [
            ("existing", [])
        ]
        assert preview_result["annotation_rows"] == 2
        assert preview_result["expected_inserts"] == 1

        blocked = _wait_for_job(
            client,
            client.post(
                "/api/v1/packages/build", json=_existing_build_request(dry_run=False)
            ).json()["job_id"],
        )
        assert blocked["status"] == "failed"
        assert "already exists in Incoming" in blocked["error_message"]


def test_build_creates_new_attribute_and_entry(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    _create_v3_database(settings.data_root)
    package = settings.data_root / "Incoming" / "Annotations" / "emission_batch_v1"
    request = {
        "package_name": "emission_batch_v1",
        "source_file": "emission.csv",
        "identifier_column_index": 0,
        "processor_name": "DeepMPP processor",
        "processor_version": "1.0",
        "mappings": [
            {
                "column_index": 1,
                "column_name": "Emi_pred",
                "attribute": {
                    "mode": "new",
                    "attribute_key": "emission_wavelength",
                    "attribute_name": "Emission Wavelength",
                    "value_type": "number",
                    "unit": "nm",
                },
                "entry": {
                    "mode": "new",
                    "entry_key": "emission_wavelength.deepmpp.CS(C)=O",
                    "annotation_kind": "prediction",
                    "method_name": "DeepMPP",
                    "conditions": {"solvent_smiles": "CS(C)=O"},
                },
            }
        ],
        "dry_run": False,
    }

    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/source-files",
            files={"file": ("emission.csv", b"SMILES,Emi_pred\nCCO,353.9\n", "text/csv")},
        )
        built = _wait_for_job(
            client, client.post("/api/v1/packages/build", json=request).json()["job_id"]
        )
        assert built["status"] == "completed"
        result = built["result"]
        assert (result["attributes_new"], result["entries_new"]) == (1, 1)
        assert (result["attributes_existing"], result["entries_existing"]) == (0, 0)
        assert result["expected_inserts"] == 1

        manifest = json.loads((package / "annotation_manifest.json").read_text(encoding="utf-8"))
        assert manifest["attributes"][0]["attribute_key"] == "emission_wavelength"
        assert manifest["entries"][0]["entry_key"] == "emission_wavelength.deepmpp.CS(C)=O"

        listed = _wait_for_job(client, client.post("/api/v1/packages/query").json()["job_id"])
        package_id = next(
            item["package_id"]
            for item in listed["result"]["items"]
            if item["package_name"] == "emission_batch_v1"
        )
        package_preview = _wait_for_job(
            client, client.post(f"/api/v1/packages/{package_id}/preview").json()["job_id"]
        )
        preview_result = package_preview["result"]
        assert preview_result["can_import"] is True
        assert preview_result["errors"] == []
        assert [item["status"] for item in preview_result["attributes"]] == ["new"]
        assert [item["status"] for item in preview_result["entries"]] == ["new"]

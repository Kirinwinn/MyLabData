"""API tests for read-only catalog endpoints and unavailable stage-7 services."""

from pathlib import Path

from fastapi.testclient import TestClient

from mylabdata.core.config import Settings
from mylabdata.db.connection import connection
from mylabdata.db.migrate import migrate
from mylabdata.main import create_app


def test_catalog_endpoints_serialize_database_records(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
    migrate(settings)
    with connection(settings) as database_connection:
        database_connection.execute(
            "INSERT INTO Molecules (lab_id, canonical_smiles) VALUES ('L00000001', 'CCO')"
        )
        database_connection.execute(
            """
            INSERT INTO Attributes (attribute_key, attribute_name, value_type)
            VALUES ('purchased', 'Purchased', 'boolean')
            """
        )
        database_connection.execute(
            """
            INSERT INTO Entries (
                attribute_id, entry_key, annotation_kind, method_name, is_mutable
            )
            SELECT attribute_id, 'purchased.manual', 'property', 'Manual', true
            FROM Attributes WHERE attribute_key = 'purchased'
            """
        )

    with TestClient(create_app(settings)) as client:
        molecules = client.get("/api/v1/molecules").json()
        assert molecules[0]["canonical_smiles"] == "CCO"
        detail = client.get(f"/api/v1/molecules/{molecules[0]['molecule_id']}")
        assert detail.status_code == 200
        attributes = client.get("/api/v1/attributes").json()
        entries = client.get(
            f"/api/v1/attributes/{attributes[0]['attribute_id']}/entries"
        ).json()
        assert entries[0]["entry_key"] == "purchased.manual"
        assert client.get("/api/v1/stats").json()["molecules"] == 1
        assert client.get("/api/v1/imports").json() == []


def test_search_validation_and_property_job_submission_are_explicit(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)
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
        assert search.status_code == 422
        update = client.put(
            "/api/v1/molecules/1/properties/1",
            json={"value_boolean": True, "source": "manual:test"},
        )
        assert update.status_code == 202

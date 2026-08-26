"""Contract tests for the complete versioned FastAPI surface."""

import json
from pathlib import Path

from mylabdata.core.config import Settings
from mylabdata.main import create_app

EXPECTED_ROUTES = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/packages"),
    ("GET", "/api/v1/packages/{package_id}"),
    ("POST", "/api/v1/packages/{package_id}/preview"),
    ("POST", "/api/v1/packages/{package_id}/imports"),
    ("GET", "/api/v1/imports"),
    ("GET", "/api/v1/imports/{import_id}"),
    ("GET", "/api/v1/jobs/{job_id}"),
    ("GET", "/api/v1/jobs/{job_id}/events"),
    ("GET", "/api/v1/molecules"),
    ("GET", "/api/v1/molecules/{molecule_id}"),
    ("GET", "/api/v1/attributes"),
    ("GET", "/api/v1/attributes/{attribute_id}/entries"),
    ("POST", "/api/v1/search"),
    ("PUT", "/api/v1/molecules/{molecule_id}/properties/{entry_id}"),
    ("GET", "/api/v1/stats"),
}


def test_all_planned_routes_are_exposed(tmp_path: Path) -> None:
    application = create_app(Settings(data_root=tmp_path / "DryData"))
    paths = application.openapi()["paths"]
    actual = {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
    }

    assert EXPECTED_ROUTES <= actual
    assert ("POST", "/api/v1/jobs") not in actual


def test_openapi_does_not_accept_client_filesystem_paths(tmp_path: Path) -> None:
    application = create_app(Settings(data_root=tmp_path / "DryData"))
    document = json.dumps(application.openapi())

    assert "file_path" not in document
    assert "package_path" not in document
    assert "package_id" in document

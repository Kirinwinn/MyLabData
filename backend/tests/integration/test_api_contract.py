"""Contract tests for the complete versioned FastAPI surface."""

import json
from pathlib import Path

from core.config import Settings
from main import create_app

EXPECTED_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/packages/query"),
    ("POST", "/api/v1/packages/{package_id}/query"),
    ("POST", "/api/v1/packages/{package_id}/preview"),
    ("POST", "/api/v1/packages/{package_id}/imports"),
    ("POST", "/api/v1/imports/query"),
    ("POST", "/api/v1/imports/{import_id}/query"),
    ("GET", "/api/v1/jobs/{job_id}"),
    ("GET", "/api/v1/jobs/{job_id}/events"),
    ("POST", "/api/v1/molecules/query"),
    ("POST", "/api/v1/molecules/{molecule_id}/query"),
    ("POST", "/api/v1/attributes/query"),
    ("POST", "/api/v1/attributes/{attribute_id}/entries/query"),
    ("POST", "/api/v1/attributes/{attribute_id}/stats/query"),
    ("POST", "/api/v1/search"),
    ("PUT", "/api/v1/molecules/{molecule_id}/properties/{entry_id}"),
    ("POST", "/api/v1/stats/query"),
}


def test_all_planned_routes_are_exposed(tmp_path: Path) -> None:
    application = create_app(Settings(data_root=tmp_path / "DryData"))
    paths = application.openapi()["paths"]
    actual = {(method.upper(), path) for path, operations in paths.items() for method in operations}

    assert EXPECTED_ROUTES <= actual
    assert ("POST", "/api/v1/jobs") not in actual


def test_openapi_does_not_accept_client_filesystem_paths(tmp_path: Path) -> None:
    application = create_app(Settings(data_root=tmp_path / "DryData"))
    document = json.dumps(application.openapi())

    assert "file_path" not in document
    assert "package_path" not in document
    assert "package_id" in document

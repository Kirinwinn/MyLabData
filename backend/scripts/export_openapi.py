"""Export the FastAPI OpenAPI document for frontend type generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from pydantic.json_schema import models_json_schema  # noqa: E402

from main import create_app  # noqa: E402
from schemas.annotations import AnnotationPackagePreview  # noqa: E402
from schemas.catalog import (  # noqa: E402
    AttributeRecord,
    AttributeStatistics,
    DatabaseStats,
    EntryRecord,
    ImportRecord,
    Molecule3DStructure,
    MoleculeAttributeAnnotation,
    MoleculeDetail,
    MoleculeSummary,
    PropertyUpdateResult,
    SearchExportResult,
    SearchResult,
)
from schemas.packages import (  # noqa: E402
    MoleculePackagePreview,
    PackageDetail,
    PackageImportResult,
    PackageSummary,
)

JOB_RESULT_MODELS = (
    MoleculePackagePreview,
    AnnotationPackagePreview,
    PackageImportResult,
    PropertyUpdateResult,
    ImportRecord,
    MoleculeSummary,
    MoleculeDetail,
    Molecule3DStructure,
    MoleculeAttributeAnnotation,
    AttributeRecord,
    EntryRecord,
    AttributeStatistics,
    DatabaseStats,
    SearchResult,
    SearchExportResult,
    PackageSummary,
    PackageDetail,
)


def build_openapi_document() -> dict:
    """Include concrete job results that JobRecord's generic JSON cannot expose."""
    document = create_app().openapi()
    _, definitions = models_json_schema(
        [(model, "validation") for model in JOB_RESULT_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    document.setdefault("components", {}).setdefault("schemas", {}).update(
        definitions.get("$defs", {})
    )
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()

    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_openapi_document(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

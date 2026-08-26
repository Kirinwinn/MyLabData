"""Unit tests for the Annotation Package JSON contract."""

import pytest
from pydantic import ValidationError

from mylabdata.contracts.manifest import AnnotationManifest


def valid_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "processor_name": "RDKitAdapter",
        "processor_version": "1.0",
        "attributes": [
            {
                "attribute_key": "molecular_weight",
                "attribute_name": "Molecular Weight",
                "value_type": "number",
                "unit": "Da",
            }
        ],
        "entries": [
            {
                "entry_key": "molecular_weight.rdkit",
                "attribute_key": "molecular_weight",
                "annotation_kind": "calculation",
                "method_name": "RDKit",
                "conditions": {},
            }
        ],
        "data_files": ["annotations.parquet"],
        "generated_at": "2026-08-26T10:00:00+08:00",
    }


def test_manifest_accepts_complete_definition_graph() -> None:
    manifest = AnnotationManifest.model_validate(valid_manifest())
    assert manifest.entries[0].attribute_key == "molecular_weight"


def test_manifest_rejects_unknown_entry_attribute() -> None:
    payload = valid_manifest()
    payload["entries"][0]["attribute_key"] = "unknown"
    with pytest.raises(ValidationError, match="unknown attributes"):
        AnnotationManifest.model_validate(payload)


def test_manifest_rejects_shards_until_supported() -> None:
    payload = valid_manifest()
    payload["data_files"] = ["annotations_0001.parquet"]
    with pytest.raises(ValidationError, match="annotations.parquet"):
        AnnotationManifest.model_validate(payload)

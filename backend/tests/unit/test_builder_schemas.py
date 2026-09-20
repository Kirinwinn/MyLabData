"""Validation tests for the package builder request contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.builder import PackageBuildRequest

_BASE_MAPPING = {
    "column_index": 1,
    "column_name": "Abs_pred",
    "attribute": {"mode": "existing", "attribute_key": "absorption_wavelength"},
    "entry": {"mode": "existing", "entry_key": "absorption_wavelength.deepmpp.CS(C)=O"},
}


def _request(**overrides: object) -> dict:
    payload = {
        "package_name": "batch_v1",
        "source_file": "results.csv",
        "identifier_column_index": 0,
        "processor_name": "DeepMPP processor",
        "processor_version": "1.0",
        "mappings": [dict(_BASE_MAPPING)],
    }
    payload.update(overrides)
    return payload


def test_accepts_existing_and_new_choices() -> None:
    request = PackageBuildRequest.model_validate(_request())
    assert request.mappings[0].attribute.mode == "existing"
    assert request.dry_run is False


def test_rejects_duplicate_or_identifier_mappings() -> None:
    duplicated = _request(
        mappings=[
            dict(_BASE_MAPPING),
            {**_BASE_MAPPING, "column_name": "Abs_copy"},
        ]
    )
    with pytest.raises(ValidationError, match="only be mapped once"):
        PackageBuildRequest.model_validate(duplicated)

    identifier = _request(
        mappings=[{**_BASE_MAPPING, "column_index": 0}],
    )
    with pytest.raises(ValidationError, match="identifier column"):
        PackageBuildRequest.model_validate(identifier)


def test_rejects_unsafe_package_names() -> None:
    for name in ("../escape", "with/slash", "", " leading"):
        with pytest.raises(ValidationError):
            PackageBuildRequest.model_validate(_request(package_name=name))


def test_new_attribute_requires_name_and_type() -> None:
    mapping = {
        **_BASE_MAPPING,
        "attribute": {"mode": "new", "attribute_key": "new_metric"},
    }
    with pytest.raises(ValidationError, match="attribute_name is required"):
        PackageBuildRequest.model_validate(_request(mappings=[mapping]))

    mapping = {
        **_BASE_MAPPING,
        "attribute": {
            "mode": "new",
            "attribute_key": "new_metric",
            "attribute_name": "New Metric",
        },
    }
    with pytest.raises(ValidationError, match="value_type is required"):
        PackageBuildRequest.model_validate(_request(mappings=[mapping]))


def test_new_entry_requires_kind_and_method() -> None:
    mapping = {
        **_BASE_MAPPING,
        "entry": {"mode": "new", "entry_key": "absorption_wavelength.batch.v1"},
    }
    with pytest.raises(ValidationError, match="annotation_kind is required"):
        PackageBuildRequest.model_validate(_request(mappings=[mapping]))

    mapping = {
        **_BASE_MAPPING,
        "entry": {
            "mode": "new",
            "entry_key": "absorption_wavelength.batch.v1",
            "annotation_kind": "prediction",
        },
    }
    with pytest.raises(ValidationError, match="method_name is required"):
        PackageBuildRequest.model_validate(_request(mappings=[mapping]))


def test_only_property_entries_may_be_mutable() -> None:
    mapping = {
        **_BASE_MAPPING,
        "entry": {
            "mode": "new",
            "entry_key": "absorption_wavelength.batch.v1",
            "annotation_kind": "prediction",
            "method_name": "Batch",
            "is_mutable": True,
        },
    }
    with pytest.raises(ValidationError, match="only property entries may be mutable"):
        PackageBuildRequest.model_validate(_request(mappings=[mapping]))

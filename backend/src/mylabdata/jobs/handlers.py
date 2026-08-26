"""Built-in adapters between job records and existing workflows."""

from pathlib import Path
from typing import Any

from mylabdata.jobs.manager import JobContext, JobManager, JobOutcome
from mylabdata.schemas.catalog import PropertyUpdateRequest
from mylabdata.services.annotation_importer import import_annotation_package
from mylabdata.services.annotation_preview import preview_annotation_package
from mylabdata.services.molecule_importer import (
    import_molecule_file,
    preview_molecule_file,
)
from mylabdata.services.package_scanner import get_package
from mylabdata.services.property_editor import update_property


def register_builtin_handlers(manager: JobManager) -> None:
    """Register workflows that already exist in the current backend phase."""
    manager.register("molecule_import", _molecule_import)
    manager.register("molecule_preview", _molecule_preview)
    manager.register("annotation_preview", _annotation_preview)
    manager.register("annotation_import", _annotation_import)
    manager.register("property_update", _property_update)


def _molecule_import(
    context: JobContext,
    payload: dict[str, Any],
) -> JobOutcome:
    file_path = _package_path(context, payload, "molecules")
    context.set_status("validating", 0.15, "Previewing Molecules file")
    preview = preview_molecule_file(file_path, context.manager.settings)
    context.raise_if_cancelled()
    context.set_status("importing", 0.55, "Importing Molecules")
    result = import_molecule_file(
        file_path,
        context.manager.settings,
        expected_file_hash=preview.file_hash,
    )
    return JobOutcome(
        result=result.model_dump(mode="json"),
        message="Molecules import completed",
    )


def _annotation_preview(
    context: JobContext,
    payload: dict[str, Any],
) -> JobOutcome:
    package_path = _package_path(context, payload, "annotations")
    context.set_status("validating", 0.2, "Validating Annotation Package")
    preview = preview_annotation_package(package_path, context.manager.settings)
    if preview.errors:
        raise ValueError("; ".join(preview.errors))
    return JobOutcome(
        result=preview.model_dump(mode="json"),
        status="waiting_confirmation",
        message="Annotation Package is ready for confirmation",
    )


def _molecule_preview(
    context: JobContext,
    payload: dict[str, Any],
) -> JobOutcome:
    file_path = _package_path(context, payload, "molecules")
    context.set_status("validating", 0.2, "Validating Molecules file")
    preview = preview_molecule_file(file_path, context.manager.settings)
    return JobOutcome(
        result=preview.model_dump(mode="json"),
        message="Molecules preview completed",
    )


def _annotation_import(
    context: JobContext,
    payload: dict[str, Any],
) -> JobOutcome:
    package_path = _package_path(context, payload, "annotations")
    preview_token = payload.get("preview_token")
    if not isinstance(preview_token, str) or not preview_token:
        raise ValueError("payload.preview_token is required")
    context.set_status("validating", 0.15, "Revalidating Annotation Package")
    context.raise_if_cancelled()
    context.set_status("importing", 0.5, "Importing Annotations")
    result = import_annotation_package(
        package_path,
        preview_token,
        context.manager.settings,
    )
    return JobOutcome(
        result=result.model_dump(mode="json"),
        message="Annotation import completed",
    )


def _package_path(
    context: JobContext,
    payload: dict[str, Any],
    expected_kind: str,
) -> Path:
    package_id = payload.get("package_id")
    if not isinstance(package_id, str) or not package_id:
        raise ValueError("payload.package_id must be a non-empty string")
    detail, path = get_package(package_id, context.manager.settings)
    if detail.package_kind != expected_kind:
        raise ValueError(f"Package {package_id} is not a {expected_kind} package")
    return path


def _property_update(
    context: JobContext,
    payload: dict[str, Any],
) -> JobOutcome:
    try:
        molecule_id = int(payload["molecule_id"])
        entry_id = int(payload["entry_id"])
        request = PropertyUpdateRequest.model_validate(payload["request"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid property update job payload") from exc
    context.set_status("importing", 0.5, "Updating mutable Property")
    result = update_property(
        molecule_id,
        entry_id,
        request,
        context.manager.settings,
    )
    return JobOutcome(
        result=result.model_dump(mode="json"),
        message="Property update completed",
    )

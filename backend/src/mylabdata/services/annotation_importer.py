"""Atomic, set-based import of a confirmed Annotation Package."""

from pathlib import Path

import duckdb

from mylabdata.contracts.manifest import AnnotationManifest
from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import (
    AnnotationImportError,
    AnnotationPackageError,
    ConflictError,
    PreviewTokenError,
)
from mylabdata.db.annotation_preview import (
    STAGED_ANNOTATIONS,
    annotation_metrics,
    compare_catalog,
    validate_and_stage_annotations,
)
from mylabdata.db.annotations import (
    create_annotation_import,
    insert_staged_annotations,
    register_manifest_catalog,
    stage_manifest_definitions,
)
from mylabdata.db.connection import connection
from mylabdata.schemas.annotations import AnnotationImportResult
from mylabdata.services.annotation_preview import (
    assert_annotation_preview_current,
    calculate_package_hash,
    preview_annotation_package,
)


def import_annotation_package(
    package_path: Path,
    preview_token: str,
    settings: Settings | None = None,
) -> AnnotationImportResult:
    """Revalidate, atomically import, then move one Annotation Package."""
    resolved_settings = settings or get_settings()
    assert_annotation_preview_current(package_path, preview_token, resolved_settings)
    preview = preview_annotation_package(package_path, resolved_settings)
    if not preview.can_import:
        destination = _move_invalid_package(package_path, resolved_settings)
        detail = "; ".join(preview.errors)
        raise AnnotationPackageError(
            f"Invalid Annotation Package moved to {destination.name}: {detail}"
        )

    manifest = AnnotationManifest.model_validate_json(
        (package_path / "annotation_manifest.json").read_text(encoding="utf-8")
    )
    created_sources = 0
    created_attributes = 0
    created_entries = 0
    import_id = 0
    inserted = 0

    try:
        with connection(resolved_settings) as database_connection:
            database_connection.execute("BEGIN TRANSACTION")
            try:
                stage_manifest_definitions(database_connection, manifest)
                attribute_items, entry_items, entry_conflicts = compare_catalog(
                    database_connection,
                    manifest,
                )
                if any(item.status == "conflict" for item in attribute_items):
                    raise ConflictError("Attribute catalog changed after preview")
                if entry_conflicts or any(
                    item.status == "conflict" for item in entry_items
                ):
                    raise ConflictError("Entry catalog changed after preview")

                (
                    created_sources,
                    created_attributes,
                    created_entries,
                ) = register_manifest_catalog(
                    database_connection,
                    processor_name=manifest.processor_name,
                )
                validate_and_stage_annotations(
                    database_connection,
                    package_path / "annotations.parquet",
                )
                if calculate_package_hash(package_path) != preview.package_hash:
                    raise PreviewTokenError(
                        "Annotation Package changed while the import was staged"
                    )
                metrics = annotation_metrics(database_connection, manifest, set())
                _assert_preview_matches(preview, metrics)
                inserted = insert_staged_annotations(
                    database_connection,
                    STAGED_ANNOTATIONS,
                )
                if inserted != preview.expected_inserts:
                    raise PreviewTokenError(
                        "Annotation insert count no longer matches the confirmed preview"
                    )
                import_id = create_annotation_import(
                    database_connection,
                    package_name=preview.package_name,
                    package_hash=preview.package_hash,
                    processor_name=manifest.processor_name,
                    total_rows=preview.annotation_rows,
                    duplicate_rows=preview.duplicate_annotations,
                    existing_rows=preview.existing_annotations,
                    expected_rows=inserted,
                )
                database_connection.execute("COMMIT")
            except Exception:
                database_connection.execute("ROLLBACK")
                raise
    except (PreviewTokenError, ConflictError):
        raise
    except (duckdb.Error, OSError) as exc:
        raise AnnotationImportError(
            f"Annotation import rolled back; package remains in Incoming: {exc}"
        ) from exc
    except Exception as exc:
        raise AnnotationImportError(
            f"Annotation import rolled back; package remains in Incoming: {exc}"
        ) from exc

    warnings = list(preview.warnings)
    destination: Path | None = None
    try:
        if calculate_package_hash(package_path) != preview.package_hash:
            warnings.append(
                "Database commit succeeded, but the package changed afterwards; "
                "it remains in Incoming and was not moved"
            )
            return AnnotationImportResult(
                import_id=import_id,
                package_name=preview.package_name,
                package_hash=preview.package_hash,
                annotation_rows=preview.annotation_rows,
                inserted_annotations=inserted,
                existing_annotations=preview.existing_annotations,
                duplicate_annotations=preview.duplicate_annotations,
                unlinkable_molecules=preview.unlinkable_molecules,
                created_sources=created_sources,
                created_attributes=created_attributes,
                created_entries=created_entries,
                package_moved=False,
                destination=None,
                warnings=warnings,
            )
        destination = _move_package(
            package_path,
            resolved_settings.processed_annotations_directory,
            preview.package_hash,
        )
    except (OSError, AnnotationPackageError) as exc:
        warnings.append(
            "Database commit succeeded, but the package could not be moved; "
            f"it remains retryable in Incoming: {exc}"
        )

    return AnnotationImportResult(
        import_id=import_id,
        package_name=preview.package_name,
        package_hash=preview.package_hash,
        annotation_rows=preview.annotation_rows,
        inserted_annotations=inserted,
        existing_annotations=preview.existing_annotations,
        duplicate_annotations=preview.duplicate_annotations,
        unlinkable_molecules=preview.unlinkable_molecules,
        created_sources=created_sources,
        created_attributes=created_attributes,
        created_entries=created_entries,
        package_moved=destination is not None,
        destination=(
            destination.relative_to(resolved_settings.data_root).as_posix()
            if destination is not None
            else None
        ),
        warnings=warnings,
    )


def _assert_preview_matches(preview, metrics: dict[str, int]) -> None:
    expected = {
        "annotation_rows": preview.annotation_rows,
        "linkable_molecules": preview.linkable_molecules,
        "unlinkable_molecules": preview.unlinkable_molecules,
        "duplicate_annotations": preview.duplicate_annotations,
        "existing_annotations": preview.existing_annotations,
        "expected_inserts": preview.expected_inserts,
    }
    actual = {key: metrics[key] for key in expected}
    if actual != expected:
        raise PreviewTokenError(
            "Database or package contents changed after preview; preview again"
        )


def _move_invalid_package(package_path: Path, settings: Settings) -> Path:
    try:
        return _move_package(
            package_path,
            settings.failed_annotations_directory,
            "invalid",
        )
    except OSError as exc:
        raise AnnotationPackageError(
            f"Annotation Package is invalid and could not be moved to Failed: {exc}"
        ) from exc


def _move_package(package_path: Path, root: Path, suffix: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / package_path.name
    if destination.exists():
        destination = root / f"{package_path.name}__{suffix[:12]}"
    counter = 2
    candidate = destination
    while candidate.exists():
        candidate = destination.with_name(f"{destination.name}__{counter}")
        counter += 1
    return package_path.replace(candidate)

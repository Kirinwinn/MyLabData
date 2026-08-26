"""Non-mutating validation and preview of Annotation Packages."""

import json
from hashlib import sha256
from pathlib import Path

import duckdb
from pydantic import ValidationError as PydanticValidationError

from mylabdata.contracts.manifest import AnnotationManifest, ProcessingReport
from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import AnnotationPackageError, PreviewTokenError
from mylabdata.db.annotation_preview import (
    annotation_metrics,
    compare_catalog,
    validate_and_stage_annotations,
)
from mylabdata.db.connection import connection
from mylabdata.schemas.annotations import AnnotationPackagePreview

MANIFEST_FILE = "annotation_manifest.json"
ANNOTATIONS_FILE = "annotations.parquet"
REPORT_FILE = "processing_report.json"
REJECTED_FILE = "rejected.parquet"
REQUIRED_FILES = {MANIFEST_FILE, ANNOTATIONS_FILE, REPORT_FILE}
ALLOWED_FILES = REQUIRED_FILES | {REJECTED_FILE}
HASH_CHUNK_SIZE = 1024 * 1024
TOKEN_PREFIX = "annotation-preview-v1"


def calculate_package_hash(package_path: Path) -> str:
    """Hash relative filenames, sizes, and contents in deterministic order."""
    digest = sha256()
    files = sorted(package_path.iterdir(), key=lambda item: item.name)
    for file_path in files:
        if file_path.is_symlink() or not file_path.is_file():
            raise AnnotationPackageError(
                f"Package entries must be regular files: {file_path.name}"
            )
        encoded_name = file_path.name.encode("utf-8")
        size = file_path.stat().st_size
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(size.to_bytes(8, "big"))
        with file_path.open("rb") as source:
            while chunk := source.read(HASH_CHUNK_SIZE):
                digest.update(chunk)
    return digest.hexdigest()


def preview_annotation_package(
    package_path: Path,
    settings: Settings | None = None,
) -> AnnotationPackagePreview:
    """Return a complete preview without modifying persistent database data."""
    resolved_settings = settings or get_settings()
    package = _validated_package_path(package_path, resolved_settings)
    package_hash = calculate_package_hash(package)
    token = _make_preview_token(package.name, package_hash)
    warnings: list[str] = []
    errors = _structure_errors(package)
    manifest = _read_contract(package / MANIFEST_FILE, AnnotationManifest, errors)
    report = _read_contract(package / REPORT_FILE, ProcessingReport, errors)

    empty = {
        "annotation_rows": 0,
        "linkable_molecules": 0,
        "unlinkable_molecules": 0,
        "duplicate_annotations": 0,
        "existing_annotations": 0,
        "expected_inserts": 0,
    }
    attributes = []
    entries = []
    metrics = empty

    if manifest is not None and report is not None and not errors:
        warnings.extend(report.warnings)
        if report.status != "completed":
            errors.append("processing_report.json status is not completed")
        try:
            with connection(resolved_settings, read_only=True) as database_connection:
                validate_and_stage_annotations(
                    database_connection,
                    package / ANNOTATIONS_FILE,
                )
                attributes, entries, entry_conflicts = compare_catalog(
                    database_connection,
                    manifest,
                )
                attribute_conflicts = {
                    item.definition.attribute_key
                    for item in attributes
                    if item.status == "conflict"
                }
                blocked_entries = entry_conflicts | {
                    item.definition.entry_key
                    for item in entries
                    if item.definition.attribute_key in attribute_conflicts
                }
                metrics = annotation_metrics(
                    database_connection,
                    manifest,
                    blocked_entries,
                )
                _validate_rejected_file(database_connection, package, report, errors)
                _append_source_warnings(database_connection, manifest, warnings)
        except (AnnotationPackageError, duckdb.Error) as exc:
            errors.append(str(exc))

        if any(item.status == "conflict" for item in attributes):
            errors.append("Manifest contains conflicting Attribute definitions")
        if any(item.status == "conflict" for item in entries):
            errors.append("Manifest contains conflicting Entry definitions")
        if metrics.get("invalid_rows", 0):
            errors.append(
                f"annotations.parquet contains {metrics['invalid_rows']} invalid rows"
            )
        if metrics.get("conflicting_duplicate_groups", 0):
            errors.append(
                "annotations.parquet contains duplicate keys with conflicting values"
            )
        if metrics["annotation_rows"] != report.output_annotations:
            errors.append(
                "processing_report output_annotations does not match Parquet row count"
            )
        if metrics["duplicate_annotations"] != report.duplicate_rows:
            warnings.append(
                "processing_report duplicate_rows differs from package preview"
            )

    final_hash = calculate_package_hash(package)
    if final_hash != package_hash:
        raise AnnotationPackageError("Annotation Package changed during preview")

    return AnnotationPackagePreview(
        package_name=package.name,
        package_hash=package_hash,
        preview_token=token,
        annotation_rows=metrics["annotation_rows"],
        attributes=attributes,
        entries=entries,
        linkable_molecules=metrics["linkable_molecules"],
        unlinkable_molecules=metrics["unlinkable_molecules"],
        duplicate_annotations=metrics["duplicate_annotations"],
        existing_annotations=metrics["existing_annotations"],
        expected_inserts=metrics["expected_inserts"],
        warnings=list(dict.fromkeys(warnings)),
        errors=list(dict.fromkeys(errors)),
        can_import=not errors,
    )


def assert_annotation_preview_current(
    package_path: Path,
    preview_token: str,
    settings: Settings | None = None,
) -> str:
    """Reject a token if its package name or content hash has changed."""
    resolved_settings = settings or get_settings()
    package = _validated_package_path(package_path, resolved_settings)
    expected = _make_preview_token(package.name, calculate_package_hash(package))
    if preview_token != expected:
        raise PreviewTokenError(
            "Preview token is invalid or the Annotation Package has changed"
        )
    return preview_token.removeprefix(f"{TOKEN_PREFIX}:{package.name}:")


def _validated_package_path(package_path: Path, settings: Settings) -> Path:
    try:
        package = package_path.resolve(strict=True)
    except OSError as exc:
        raise AnnotationPackageError(
            f"Annotation Package does not exist: {package_path}"
        ) from exc
    incoming = settings.incoming_annotations_directory.resolve()
    if not package.is_dir() or not package.is_relative_to(incoming):
        raise AnnotationPackageError(
            f"Annotation Package must be a directory inside {incoming}"
        )
    return package


def _structure_errors(package: Path) -> list[str]:
    names = {item.name for item in package.iterdir()}
    missing = sorted(REQUIRED_FILES - names)
    unexpected = sorted(names - ALLOWED_FILES)
    errors = []
    if missing:
        errors.append(f"Missing required package files: {missing}")
    if unexpected:
        errors.append(f"Unexpected package entries: {unexpected}")
    return errors


def _read_contract(path: Path, model: type, errors: list[str]):
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(payload)
    except (OSError, json.JSONDecodeError, PydanticValidationError) as exc:
        errors.append(f"Invalid {path.name}: {exc}")
        return None


def _validate_rejected_file(
    database_connection: duckdb.DuckDBPyConnection,
    package: Path,
    report: ProcessingReport,
    errors: list[str],
) -> None:
    rejected_path = package / REJECTED_FILE
    if report.rejected_rows > 0 and not rejected_path.is_file():
        errors.append("processing_report declares rejected rows but rejected.parquet is missing")
        return
    if not rejected_path.is_file():
        return
    try:
        relation = database_connection.read_parquet(str(rejected_path))
    except duckdb.Error as exc:
        errors.append(f"Cannot read rejected.parquet: {exc}")
        return
    required = {
        "source_row",
        "smiles",
        "output_key",
        "raw_value",
        "error_code",
        "error_message",
    }
    missing = sorted(required - set(relation.columns))
    if missing:
        errors.append(f"rejected.parquet is missing columns: {missing}")
    rows = int(relation.aggregate("count(*)").fetchone()[0])
    if rows != report.rejected_rows:
        errors.append("processing_report rejected_rows does not match rejected.parquet")


def _append_source_warnings(
    database_connection: duckdb.DuckDBPyConnection,
    manifest: AnnotationManifest,
    warnings: list[str],
) -> None:
    source_keys = sorted({item.source_key for item in manifest.entries if item.source_key})
    if not source_keys:
        return
    placeholders = ", ".join("?" for _ in source_keys)
    existing = {
        row[0]
        for row in database_connection.execute(
            f"SELECT source_key FROM Sources WHERE source_key IN ({placeholders})",
            source_keys,
        ).fetchall()
    }
    missing = sorted(set(source_keys) - existing)
    if missing:
        warnings.append(f"Manifest references new Sources: {missing}")


def _make_preview_token(package_name: str, package_hash: str) -> str:
    return f"{TOKEN_PREFIX}:{package_name}:{package_hash}"

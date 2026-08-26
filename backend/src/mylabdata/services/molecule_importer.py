"""Preview and transactional import workflow for Molecules Parquet files."""

from hashlib import sha256
from pathlib import Path

import duckdb

from mylabdata.core.config import Settings, get_settings
from mylabdata.core.exceptions import MoleculeFileError, MoleculeImportError
from mylabdata.db.connection import connection
from mylabdata.db.imports import (
    complete_molecule_import,
    create_molecule_import,
    fail_molecule_import,
)
from mylabdata.db.migrate import migrate
from mylabdata.db.molecules import (
    insert_staged_molecules,
    molecule_preview_counts,
    stage_molecule_file,
)
from mylabdata.schemas.molecules import MoleculeImportPreview, MoleculeImportResult

HASH_CHUNK_SIZE = 1024 * 1024
DEFAULT_PROCESSOR_NAME = "mylabdata.molecule_importer"


def calculate_file_hash(file_path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file without loading it at once."""
    digest = sha256()
    with file_path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_incoming_file(file_path: Path, settings: Settings) -> Path:
    """Resolve one safe Parquet path beneath Incoming/Molecules."""
    try:
        resolved_path = file_path.resolve(strict=True)
    except OSError as exc:
        raise MoleculeFileError(f"Molecules file does not exist: {file_path}") from exc

    if not resolved_path.is_file():
        raise MoleculeFileError(f"Molecules path is not a file: {resolved_path}")
    if resolved_path.suffix.casefold() != ".parquet":
        raise MoleculeFileError("Molecules input must use the .parquet extension")

    incoming_directory = settings.incoming_molecules_directory.resolve()
    if not resolved_path.is_relative_to(incoming_directory):
        raise MoleculeFileError(
            f"Molecules file must be inside {settings.incoming_molecules_directory}"
        )
    return resolved_path


def _preview_with_connection(
    database_connection: duckdb.DuckDBPyConnection,
    file_path: Path,
) -> MoleculeImportPreview:
    """Stage one stable file revision and calculate preview counts."""
    stat_before = file_path.stat()
    stage_molecule_file(database_connection, file_path)
    file_hash = calculate_file_hash(file_path)
    stat_after = file_path.stat()
    if (
        stat_before.st_size != stat_after.st_size
        or stat_before.st_mtime_ns != stat_after.st_mtime_ns
    ):
        raise MoleculeFileError("Molecules file changed while it was being read")

    counts = molecule_preview_counts(database_connection)
    return MoleculeImportPreview(
        file_path=file_path,
        file_name=file_path.name,
        file_hash=file_hash,
        **counts,
    )


def preview_molecule_file(
    file_path: Path,
    settings: Settings | None = None,
) -> MoleculeImportPreview:
    """Validate and preview a file without changing business data."""
    resolved_settings = settings or get_settings()
    resolved_path = _validated_incoming_file(file_path, resolved_settings)
    migrate(resolved_settings)
    with connection(resolved_settings) as database_connection:
        return _preview_with_connection(database_connection, resolved_path)


def import_molecule_file(
    file_path: Path,
    settings: Settings | None = None,
    *,
    expected_file_hash: str | None = None,
    source_id: int | None = None,
    processor_name: str = DEFAULT_PROCESSOR_NAME,
) -> MoleculeImportResult:
    """Preview and atomically import distinct new molecules from one Parquet file."""
    resolved_settings = settings or get_settings()
    resolved_path = _validated_incoming_file(file_path, resolved_settings)
    migrate(resolved_settings)

    with connection(resolved_settings) as database_connection:
        preview = _preview_with_connection(database_connection, resolved_path)
        if expected_file_hash is not None and preview.file_hash != expected_file_hash:
            raise MoleculeFileError("Molecules file hash no longer matches its preview")

        import_id = create_molecule_import(
            database_connection,
            source_id=source_id,
            file_name=preview.file_name,
            file_hash=preview.file_hash,
            processor_name=processor_name,
            total_rows=preview.total_rows,
            valid_rows=preview.valid_rows,
            new_rows=preview.new_rows,
            existing_rows=preview.existing_rows,
            duplicate_rows=preview.duplicate_rows,
            invalid_rows=preview.invalid_rows,
        )

        database_connection.execute("BEGIN TRANSACTION")
        try:
            inserted_rows = insert_staged_molecules(database_connection)
            complete_molecule_import(
                database_connection,
                import_id=import_id,
                inserted_rows=inserted_rows,
                invalid_rows=preview.invalid_rows,
            )
            database_connection.execute("COMMIT")
        except Exception as exc:
            database_connection.execute("ROLLBACK")
            fail_molecule_import(
                database_connection,
                import_id=import_id,
                total_rows=preview.total_rows,
                error_message=str(exc),
            )
            raise MoleculeImportError(
                f"Molecules import {import_id} rolled back: {exc}"
            ) from exc

    return MoleculeImportResult(
        **preview.model_dump(),
        import_id=import_id,
        inserted_rows=inserted_rows,
    )

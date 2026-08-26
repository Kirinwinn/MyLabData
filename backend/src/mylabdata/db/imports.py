"""DuckDB audit operations for file imports."""

import duckdb


def create_molecule_import(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    source_id: int | None,
    file_name: str,
    file_hash: str,
    processor_name: str,
    total_rows: int,
    valid_rows: int,
    new_rows: int,
    existing_rows: int,
    duplicate_rows: int,
    invalid_rows: int,
) -> int:
    """Create a durable processing audit record before the data transaction."""
    return int(
        database_connection.execute(
            """
            INSERT INTO Imports (
                source_id,
                file_name,
                file_hash,
                data_type,
                status,
                processor_name,
                total_rows,
                valid_rows,
                new_rows,
                existing_rows,
                duplicate_rows,
                accepted_rows,
                failed_rows
            )
            VALUES (
                ?, ?, ?, 'molecules', 'processing', ?,
                ?, ?, ?, ?, ?, 0, ?
            )
            RETURNING import_id
            """,
            [
                source_id,
                file_name,
                file_hash,
                processor_name,
                total_rows,
                valid_rows,
                new_rows,
                existing_rows,
                duplicate_rows,
                invalid_rows,
            ],
        ).fetchone()[0]
    )


def complete_molecule_import(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    import_id: int,
    inserted_rows: int,
    invalid_rows: int,
) -> None:
    """Mark an import completed inside the molecule write transaction."""
    database_connection.execute(
        """
        UPDATE Imports
        SET status = 'completed',
            accepted_rows = ?,
            failed_rows = ?,
            error_message = NULL,
            finished_at = CURRENT_TIMESTAMP
        WHERE import_id = ? AND status = 'processing'
        """,
        [inserted_rows, invalid_rows, import_id],
    )


def fail_molecule_import(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    import_id: int,
    total_rows: int,
    error_message: str,
) -> None:
    """Persist failure after the molecule write transaction has rolled back."""
    database_connection.execute(
        """
        UPDATE Imports
        SET status = 'failed',
            accepted_rows = 0,
            failed_rows = ?,
            error_message = ?,
            finished_at = CURRENT_TIMESTAMP
        WHERE import_id = ? AND status = 'processing'
        """,
        [total_rows, error_message, import_id],
    )

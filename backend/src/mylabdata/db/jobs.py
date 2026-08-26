"""Persistent DuckDB operations for background job coordination."""

import json
from typing import Any

import duckdb

from mylabdata.schemas.jobs import JobRecord, JobStatus

ACTIVE_STATUSES = ("queued", "validating", "waiting_confirmation", "importing")
TERMINAL_STATUSES = ("completed", "failed", "cancelled")


def create_job(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    job_id: str,
    job_type: str,
    payload: dict[str, Any],
) -> JobRecord:
    database_connection.execute(
        """
        INSERT INTO Jobs (job_id, job_type, status, payload_json)
        VALUES (?, ?, 'queued', ?)
        """,
        [job_id, job_type, json.dumps(payload, ensure_ascii=False)],
    )
    return get_job(database_connection, job_id)


def get_job(
    database_connection: duckdb.DuckDBPyConnection,
    job_id: str,
) -> JobRecord:
    row = database_connection.execute(
        """
        SELECT job_id, job_type, status, progress, message,
               CAST(payload_json AS VARCHAR), CAST(result_json AS VARCHAR),
               error_message, cancel_requested, created_at, started_at,
               finished_at, updated_at
        FROM Jobs WHERE job_id = ?
        """,
        [job_id],
    ).fetchone()
    if row is None:
        raise KeyError(job_id)
    return _record_from_row(row)


def list_jobs(
    database_connection: duckdb.DuckDBPyConnection,
    *,
    limit: int = 100,
) -> list[JobRecord]:
    rows = database_connection.execute(
        """
        SELECT job_id, job_type, status, progress, message,
               CAST(payload_json AS VARCHAR), CAST(result_json AS VARCHAR),
               error_message, cancel_requested, created_at, started_at,
               finished_at, updated_at
        FROM Jobs ORDER BY created_at DESC LIMIT ?
        """,
        [limit],
    ).fetchall()
    return [_record_from_row(row) for row in rows]


def update_job(
    database_connection: duckdb.DuckDBPyConnection,
    job_id: str,
    *,
    status: JobStatus,
    progress: float,
    message: str | None = None,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> JobRecord:
    terminal = status in TERMINAL_STATUSES
    database_connection.execute(
        """
        UPDATE Jobs
        SET status = ?, progress = ?, message = ?,
            result_json = CASE WHEN ? IS NULL THEN result_json ELSE ? END,
            error_message = ?,
            started_at = CASE
                WHEN started_at IS NULL AND ? != 'queued' THEN CURRENT_TIMESTAMP
                ELSE started_at
            END,
            finished_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
        """,
        [
            status,
            progress,
            message,
            None if result is None else True,
            None if result is None else json.dumps(result, ensure_ascii=False, default=str),
            error_message,
            status,
            terminal,
            job_id,
        ],
    )
    return get_job(database_connection, job_id)


def request_cancellation(
    database_connection: duckdb.DuckDBPyConnection,
    job_id: str,
) -> JobRecord:
    job = get_job(database_connection, job_id)
    if job.status in TERMINAL_STATUSES:
        return job
    if job.status == "queued":
        return update_job(
            database_connection,
            job_id,
            status="cancelled",
            progress=job.progress,
            message="Cancelled before execution",
        )
    database_connection.execute(
        """
        UPDATE Jobs
        SET cancel_requested = true, updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
        """,
        [job_id],
    )
    return get_job(database_connection, job_id)


def mark_interrupted_jobs_failed(
    database_connection: duckdb.DuckDBPyConnection,
) -> int:
    placeholders = ", ".join("?" for _ in ACTIVE_STATUSES)
    count = int(
        database_connection.execute(
            f"SELECT count(*) FROM Jobs WHERE status IN ({placeholders})",
            list(ACTIVE_STATUSES),
        ).fetchone()[0]
    )
    if count:
        database_connection.execute(
            f"""
            UPDATE Jobs
            SET status = 'failed',
                error_message = 'Interrupted by application restart',
                message = 'The in-process worker stopped before completion',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ({placeholders})
            """,
            list(ACTIVE_STATUSES),
        )
    return count


def _record_from_row(row: tuple[Any, ...]) -> JobRecord:
    return JobRecord(
        job_id=row[0],
        job_type=row[1],
        status=row[2],
        progress=row[3],
        message=row[4],
        payload=json.loads(row[5]),
        result=None if row[6] is None else json.loads(row[6]),
        error_message=row[7],
        cancel_requested=row[8],
        created_at=row[9],
        started_at=row[10],
        finished_at=row[11],
        updated_at=row[12],
    )

"""Persistent storage for Job work orders in the separate Jobs.duckdb file."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any

import duckdb

from jobs.schemas import JobKind, JobRecord, JobStatus
from jobs.state import can_transition, is_terminal

INTERRUPTED_STATUSES = ("queued", "validating", "running", "importing", "archiving")


class JobRepository:
    """Own the small coordination database, never the scientific DryData database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self._connection_lock = RLock()

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        # DuckDB's file lock is strict on Windows. The Job manager deliberately
        # serializes its brief metadata reads and writes until step 6 introduces
        # an explicit connection strategy for multiple query workers.
        with self._connection_lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = duckdb.connect(str(self.database_path))
            try:
                yield connection
            finally:
                connection.close()

    def initialize(self) -> None:
        """Create the standalone Job schema without running legacy migrations."""
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS Jobs (
                    job_id VARCHAR PRIMARY KEY,
                    job_type VARCHAR NOT NULL,
                    job_kind VARCHAR NOT NULL CHECK (job_kind IN ('query', 'command')),
                    status VARCHAR NOT NULL,
                    payload_json JSON NOT NULL,
                    result_json JSON,
                    progress DOUBLE NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
                    message VARCHAR,
                    error_message VARCHAR,
                    cancel_requested BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def create(
        self,
        *,
        job_id: str,
        job_type: str,
        job_kind: JobKind,
        payload: dict[str, Any],
    ) -> JobRecord:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO Jobs (job_id, job_type, job_kind, status, payload_json)
                VALUES (?, ?, ?, 'queued', ?)
                """,
                [job_id, job_type, job_kind, json.dumps(payload, ensure_ascii=False)],
            )
            return self._get(connection, job_id)

    def get(self, job_id: str) -> JobRecord:
        with self._connection() as connection:
            return self._get(connection, job_id)

    def list(self, *, limit: int = 100) -> list[JobRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT job_id, job_type, job_kind, status, progress, message,
                       CAST(payload_json AS VARCHAR), CAST(result_json AS VARCHAR),
                       error_message, cancel_requested, created_at, started_at,
                       finished_at, updated_at
                FROM Jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def count(self) -> int:
        """Return the number of persisted work orders."""
        with self._connection() as connection:
            return int(connection.execute("SELECT count(*) FROM Jobs").fetchone()[0])

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        progress: float,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> JobRecord:
        with self._connection() as connection:
            current = self._get(connection, job_id)
            if not can_transition(current.status, status):
                raise ValueError(f"Invalid Job state transition: {current.status} -> {status}")
            terminal = is_terminal(status)
            connection.execute(
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
            return self._get(connection, job_id)

    def request_cancellation(self, job_id: str) -> JobRecord:
        with self._connection() as connection:
            job = self._get(connection, job_id)
            if is_terminal(job.status):
                return job
            if job.status == "queued":
                return self._update_with_connection(
                    connection,
                    job_id,
                    status="cancelled",
                    progress=job.progress,
                    message="Cancelled before execution",
                )
            connection.execute(
                """
                UPDATE Jobs
                SET cancel_requested = true, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
                """,
                [job_id],
            )
            return self._get(connection, job_id)

    def mark_interrupted_failed(self) -> int:
        """Mark work interrupted by an in-process worker restart as failed.

        ``waiting_confirmation`` and ``archive_pending`` are deliberately kept:
        they are stable recovery states, not work that was actively running.
        """
        placeholders = ", ".join("?" for _ in INTERRUPTED_STATUSES)
        with self._connection() as connection:
            count = int(
                connection.execute(
                    f"SELECT count(*) FROM Jobs WHERE status IN ({placeholders})",
                    list(INTERRUPTED_STATUSES),
                ).fetchone()[0]
            )
            if count:
                connection.execute(
                    f"""
                    UPDATE Jobs
                    SET status = 'failed',
                        error_message = 'Interrupted by application restart',
                        message = 'The in-process worker stopped before completion',
                        finished_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status IN ({placeholders})
                    """,
                    list(INTERRUPTED_STATUSES),
                )
        return count

    def _update_with_connection(
        self,
        connection: duckdb.DuckDBPyConnection,
        job_id: str,
        *,
        status: JobStatus,
        progress: float,
        message: str | None = None,
    ) -> JobRecord:
        connection.execute(
            """
            UPDATE Jobs
            SET status = ?, progress = ?, message = ?, finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
            """,
            [status, progress, message, job_id],
        )
        return self._get(connection, job_id)

    @staticmethod
    def _get(connection: duckdb.DuckDBPyConnection, job_id: str) -> JobRecord:
        row = connection.execute(
            """
            SELECT job_id, job_type, job_kind, status, progress, message,
                   CAST(payload_json AS VARCHAR), CAST(result_json AS VARCHAR),
                   error_message, cancel_requested, created_at, started_at,
                   finished_at, updated_at
            FROM Jobs WHERE job_id = ?
            """,
            [job_id],
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return JobRepository._record_from_row(row)

    @staticmethod
    def _record_from_row(row: tuple[Any, ...]) -> JobRecord:
        return JobRecord(
            job_id=row[0],
            job_type=row[1],
            job_kind=row[2],
            status=row[3],
            progress=row[4],
            message=row[5],
            payload=json.loads(row[6]),
            result=None if row[7] is None else json.loads(row[7]),
            error_message=row[8],
            cancel_requested=row[9],
            created_at=row[10],
            started_at=row[11],
            finished_at=row[12],
            updated_at=row[13],
        )

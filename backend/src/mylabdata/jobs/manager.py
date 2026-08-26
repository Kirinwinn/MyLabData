"""Persistent, single-worker in-process job queue."""

from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from mylabdata.core.config import Settings
from mylabdata.db.connection import connection
from mylabdata.db.jobs import (
    create_job,
    get_job,
    list_jobs,
    mark_interrupted_jobs_failed,
    request_cancellation,
    update_job,
)
from mylabdata.db.migrate import migrate
from mylabdata.schemas.jobs import JobRecord, JobStatus

JobHandler = Callable[["JobContext", dict[str, Any]], "JobOutcome | None"]
STOP = object()


@dataclass(frozen=True)
class JobOutcome:
    """Optional result and final state returned by a registered handler."""

    result: dict[str, Any] | None = None
    status: JobStatus = "completed"
    message: str | None = None


class JobCancelled(Exception):
    """Internal cooperative cancellation signal."""


class JobContext:
    """Progress and cancellation controls exposed to one running handler."""

    def __init__(self, manager: "JobManager", job_id: str) -> None:
        self.manager = manager
        self.job_id = job_id

    def set_status(
        self,
        status: JobStatus,
        progress: float,
        message: str | None = None,
    ) -> JobRecord:
        self.raise_if_cancelled()
        return self.manager._update(
            self.job_id,
            status=status,
            progress=progress,
            message=message,
        )

    def raise_if_cancelled(self) -> None:
        if self.manager.get(self.job_id).cancel_requested:
            raise JobCancelled


class JobManager:
    """Run registered operations serially on one dedicated background thread."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._handlers: dict[str, JobHandler] = {}
        self._queue: Queue[str | object] = Queue()
        self._thread: Thread | None = None
        self._lifecycle_lock = Lock()
        self._accepting = False

    def register(self, job_type: str, handler: JobHandler) -> None:
        if self._accepting:
            raise RuntimeError("Handlers must be registered before the manager starts")
        if not job_type or job_type in self._handlers:
            raise ValueError(f"Invalid or duplicate job type: {job_type}")
        self._handlers[job_type] = handler

    def start(self) -> int:
        """Initialize storage, reconcile interrupted work, and start the worker."""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return 0
            migrate(self.settings)
            with connection(self.settings) as database_connection:
                interrupted = mark_interrupted_jobs_failed(database_connection)
            self._accepting = True
            self._thread = Thread(
                target=self._worker_loop,
                name="mylabdata-single-writer",
                daemon=True,
            )
            self._thread.start()
            return interrupted

    def stop(self, *, wait: bool = True) -> None:
        """Stop accepting jobs and optionally drain work queued before shutdown."""
        with self._lifecycle_lock:
            self._accepting = False
            thread = self._thread
            if thread is None:
                return
            self._queue.put(STOP)
        if wait:
            thread.join()
        with self._lifecycle_lock:
            self._thread = None

    def submit(self, job_type: str, payload: dict[str, Any]) -> JobRecord:
        if not self._accepting:
            raise RuntimeError("Background job manager is not running")
        if job_type not in self._handlers:
            raise ValueError(f"Unsupported job type: {job_type}")
        job_id = str(uuid4())
        with connection(self.settings) as database_connection:
            job = create_job(
                database_connection,
                job_id=job_id,
                job_type=job_type,
                payload=payload,
            )
        self._queue.put(job_id)
        return job

    def get(self, job_id: str) -> JobRecord:
        # DuckDB requires concurrent connections in one process to share the
        # same access configuration. This connection executes SELECT only.
        with connection(self.settings) as database_connection:
            return get_job(database_connection, job_id)

    def list(self, *, limit: int = 100) -> list[JobRecord]:
        with connection(self.settings) as database_connection:
            return list_jobs(database_connection, limit=limit)

    def cancel(self, job_id: str) -> JobRecord:
        with connection(self.settings) as database_connection:
            return request_cancellation(database_connection, job_id)

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        progress: float,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> JobRecord:
        with connection(self.settings) as database_connection:
            return update_job(
                database_connection,
                job_id,
                status=status,
                progress=progress,
                message=message,
                result=result,
                error_message=error_message,
            )

    def _worker_loop(self) -> None:
        while True:
            queued = self._queue.get()
            try:
                if queued is STOP:
                    return
                job_id = str(queued)
                job = self.get(job_id)
                if job.status != "queued":
                    continue
                context = JobContext(self, job_id)
                context.set_status("validating", 0.05, "Validating job request")
                handler = self._handlers[job.job_type]
                outcome = handler(context, job.payload) or JobOutcome()
                if outcome.status not in ("completed", "waiting_confirmation"):
                    raise RuntimeError(f"Handler returned invalid final status: {outcome.status}")
                progress = 1.0 if outcome.status == "completed" else 0.5
                self._update(
                    job_id,
                    status=outcome.status,
                    progress=progress,
                    message=outcome.message,
                    result=outcome.result,
                )
            except JobCancelled:
                self._update(
                    str(queued),
                    status="cancelled",
                    progress=0,
                    message="Cancelled by request",
                )
            except Exception as exc:
                self._update(
                    str(queued),
                    status="failed",
                    progress=0,
                    message="Background operation failed",
                    error_message=str(exc),
                )
            finally:
                self._queue.task_done()

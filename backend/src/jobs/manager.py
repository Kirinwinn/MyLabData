"""Persistent Query and Command Job queues backed by the Jobs database."""

from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from access.paths import DryDataPaths
from core.config import Settings
from jobs.repository import JobRepository
from jobs.schemas import JobKind, JobRecord, JobStatus

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
        return self.manager._update(self.job_id, status=status, progress=progress, message=message)

    def raise_if_cancelled(self) -> None:
        if self.manager.get(self.job_id).cancel_requested:
            raise JobCancelled


class JobManager:
    """Persist Jobs and run them on separate Query and Command queues."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = JobRepository(DryDataPaths(settings.data_root).jobs_database_path)
        self._handlers: dict[str, tuple[JobKind, JobHandler]] = {}
        self._query_queue: Queue[str | object] = Queue()
        self._command_queue: Queue[str | object] = Queue()
        self._threads: list[Thread] = []
        self._lifecycle_lock = Lock()
        self._accepting = False

    def register(
        self,
        job_type: str,
        handler: JobHandler,
        *,
        job_kind: JobKind = "command",
    ) -> None:
        if self._accepting:
            raise RuntimeError("Handlers must be registered before the manager starts")
        if not job_type or job_type in self._handlers:
            raise ValueError(f"Invalid or duplicate job type: {job_type}")
        self._handlers[job_type] = (job_kind, handler)

    def start(self) -> int:
        """Initialize Jobs.duckdb and start separate Query and Command workers."""
        with self._lifecycle_lock:
            if any(thread.is_alive() for thread in self._threads):
                return 0
            self.repository.initialize()
            interrupted = self.repository.mark_interrupted_failed()
            self._accepting = True
            self._threads = [
                Thread(
                    target=self._worker_loop,
                    args=(self._command_queue, "command"),
                    name="mylabdata-command-worker",
                    daemon=True,
                ),
                *[
                    Thread(
                        target=self._worker_loop,
                        args=(self._query_queue, f"query-{number}"),
                        name=f"mylabdata-query-worker-{number}",
                        daemon=True,
                    )
                    for number in range(1, self.settings.query_workers + 1)
                ],
            ]
            for thread in self._threads:
                thread.start()
            return interrupted

    def stop(self, *, wait: bool = True) -> None:
        """Stop accepting new Jobs and optionally drain already queued work."""
        with self._lifecycle_lock:
            self._accepting = False
            threads = tuple(self._threads)
            if not threads:
                return
            self._command_queue.put(STOP)
            for _ in range(self.settings.query_workers):
                self._query_queue.put(STOP)
        if wait:
            for thread in threads:
                thread.join()
        with self._lifecycle_lock:
            self._threads = []

    def submit(self, job_type: str, payload: dict[str, Any]) -> JobRecord:
        if not self._accepting:
            raise RuntimeError("Job manager is not running")
        registration = self._handlers.get(job_type)
        if registration is None:
            raise ValueError(f"Unsupported job type: {job_type}")
        job_kind, _ = registration
        job = self.repository.create(
            job_id=str(uuid4()),
            job_type=job_type,
            job_kind=job_kind,
            payload=payload,
        )
        queue = self._query_queue if job_kind == "query" else self._command_queue
        queue.put(job.job_id)
        return job

    def get(self, job_id: str) -> JobRecord:
        return self.repository.get(job_id)

    def list(self, *, limit: int = 100) -> list[JobRecord]:
        return self.repository.list(limit=limit)

    def cancel(self, job_id: str) -> JobRecord:
        return self.repository.request_cancellation(job_id)

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
        return self.repository.update(
            job_id,
            status=status,
            progress=progress,
            message=message,
            result=result,
            error_message=error_message,
        )

    def _worker_loop(self, queue: Queue[str | object], worker_name: str) -> None:
        while True:
            queued = queue.get()
            try:
                if queued is STOP:
                    return
                job_id = str(queued)
                job = self.get(job_id)
                if job.status != "queued":
                    continue
                context = JobContext(self, job_id)
                context.set_status("validating", 0.05, f"Validating Job request ({worker_name})")
                job_kind, handler = self._handlers[job.job_type]
                if job.job_kind != job_kind:
                    raise RuntimeError(f"Registered kind changed for Job type: {job.job_type}")
                outcome = handler(context, job.payload) or JobOutcome()
                if outcome.status not in ("completed", "waiting_confirmation", "archive_pending"):
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
                    message="Job operation failed",
                    error_message=str(exc),
                )
            finally:
                queue.task_done()

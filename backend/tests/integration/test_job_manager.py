"""Integration tests for persistent single-worker job coordination."""

from threading import Event, Lock
from time import monotonic, sleep

from mylabdata.core.config import Settings
from mylabdata.db.connection import connection
from mylabdata.jobs.manager import JobContext, JobManager, JobOutcome


def make_settings(tmp_path) -> Settings:
    return Settings(data_root=tmp_path / "DryData", memory_limit="1GB", threads=1)


def wait_for_status(
    manager: JobManager,
    job_id: str,
    expected: set[str],
    timeout: float = 5,
):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        job = manager.get(job_id)
        if job.status in expected:
            return job
        sleep(0.02)
    raise AssertionError(f"Job {job_id} did not reach {expected}")


def test_jobs_are_serial_and_queries_continue(tmp_path) -> None:
    settings = make_settings(tmp_path)
    release = Event()
    first_started = Event()
    state_lock = Lock()
    active = 0
    maximum_active = 0

    def controlled_handler(context: JobContext, payload: dict) -> JobOutcome:
        nonlocal active, maximum_active
        context.set_status("importing", 0.5, "Holding test transaction")
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        first_started.set()
        with connection(settings) as database_connection:
            database_connection.execute("BEGIN TRANSACTION")
            database_connection.execute(
                "INSERT INTO Molecules (lab_id, canonical_smiles) VALUES (?, ?)",
                [payload["lab_id"], payload["canonical_smiles"]],
            )
            assert release.wait(timeout=5)
            database_connection.execute("COMMIT")
        with state_lock:
            active -= 1
        return JobOutcome(result={"inserted": 1})

    manager = JobManager(settings)
    manager.register("controlled", controlled_handler)
    manager.start()
    try:
        first = manager.submit(
            "controlled",
            {"lab_id": "L00000001", "canonical_smiles": "CCO"},
        )
        assert first_started.wait(timeout=5)
        second = manager.submit(
            "controlled",
            {"lab_id": "L00000002", "canonical_smiles": "CCN"},
        )
        assert manager.get(second.job_id).status == "queued"

        with connection(settings) as database_connection:
            assert database_connection.execute(
                "SELECT count(*) FROM Molecules"
            ).fetchone() == (0,)

        release.set()
        assert wait_for_status(manager, first.job_id, {"completed"}).status == "completed"
        assert wait_for_status(manager, second.job_id, {"completed"}).status == "completed"
        assert maximum_active == 1
    finally:
        release.set()
        manager.stop()


def test_failed_job_persists_error_message(tmp_path) -> None:
    settings = make_settings(tmp_path)

    def failing_handler(context: JobContext, payload: dict) -> None:
        raise RuntimeError("injected worker failure")

    manager = JobManager(settings)
    manager.register("failure", failing_handler)
    manager.start()
    try:
        submitted = manager.submit("failure", {})
        failed = wait_for_status(manager, submitted.job_id, {"failed"})
        assert failed.error_message == "injected worker failure"
        assert failed.finished_at is not None
    finally:
        manager.stop()


def test_restart_marks_unfinished_job_failed(tmp_path) -> None:
    settings = make_settings(tmp_path)
    first_manager = JobManager(settings)
    first_manager.register("noop", lambda context, payload: JobOutcome())
    first_manager.start()
    first_manager._accepting = False
    with connection(settings) as database_connection:
        database_connection.execute(
            """
            INSERT INTO Jobs (job_id, job_type, status, payload_json)
            VALUES ('interrupted-job', 'noop', 'importing', '{}')
            """
        )
    first_manager.stop()

    restarted = JobManager(settings)
    restarted.register("noop", lambda context, payload: JobOutcome())
    assert restarted.start() == 1
    try:
        job = restarted.get("interrupted-job")
        assert job.status == "failed"
        assert job.error_message == "Interrupted by application restart"
    finally:
        restarted.stop()

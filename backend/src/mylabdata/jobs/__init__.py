"""In-process background job coordination."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mylabdata.jobs.manager import JobContext, JobManager, JobOutcome

__all__ = ["JobContext", "JobManager", "JobOutcome"]


def __getattr__(name: str) -> Any:
    """Load DuckDB-dependent manager classes only when requested."""
    if name in __all__:
        from mylabdata.jobs.manager import JobContext, JobManager, JobOutcome

        return {
            "JobContext": JobContext,
            "JobManager": JobManager,
            "JobOutcome": JobOutcome,
        }[name]
    raise AttributeError(name)

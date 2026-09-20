"""Pure state-transition policy for Job work orders."""

from jobs.schemas import JobStatus

TERMINAL_STATUSES: frozenset[JobStatus] = frozenset({"completed", "failed", "cancelled"})

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    "queued": frozenset({"validating", "failed", "cancelled"}),
    "validating": frozenset(
        {
            "validating",
            "waiting_confirmation",
            "running",
            "importing",
            "completed",
            "failed",
            "cancelled",
        }
    ),
    "waiting_confirmation": frozenset({"validating", "importing", "failed", "cancelled"}),
    "running": frozenset({"running", "waiting_confirmation", "completed", "failed", "cancelled"}),
    "importing": frozenset({"importing", "archiving", "completed", "failed", "cancelled"}),
    "archiving": frozenset({"archiving", "archive_pending", "completed", "failed"}),
    "archive_pending": frozenset({"archiving", "completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    """Return whether the documented lifecycle permits one state change."""
    return target in ALLOWED_TRANSITIONS[current]


def is_terminal(status: JobStatus) -> bool:
    """Return whether no further state changes are permitted."""
    return status in TERMINAL_STATUSES

"""Pure background-job state transition policy."""

from mylabdata.schemas.jobs import JobStatus

TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {"completed", "failed", "cancelled"}
)

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    "queued": frozenset({"validating", "failed", "cancelled"}),
    "validating": frozenset(
        {
            "validating",
            "waiting_confirmation",
            "importing",
            "completed",
            "failed",
            "cancelled",
        }
    ),
    "waiting_confirmation": frozenset({"importing", "failed", "cancelled"}),
    "importing": frozenset({"importing", "completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    """Return whether the documented lifecycle permits one state change."""
    return target in ALLOWED_TRANSITIONS[current]


def is_terminal(status: JobStatus) -> bool:
    """Return whether no further work may be reported for a state."""
    return status in TERMINAL_STATUSES

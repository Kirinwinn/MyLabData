"""Unit tests for the pure background-job state machine."""

import pytest

from mylabdata.jobs.state import can_transition, is_terminal


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("queued", "validating"),
        ("validating", "waiting_confirmation"),
        ("validating", "importing"),
        ("waiting_confirmation", "importing"),
        ("importing", "completed"),
        ("queued", "cancelled"),
        ("importing", "failed"),
    ],
)
def test_documented_job_transitions_are_allowed(current: str, target: str) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_terminal_job_states_cannot_transition(terminal: str) -> None:
    assert is_terminal(terminal)
    for target in (
        "queued",
        "validating",
        "waiting_confirmation",
        "importing",
        "completed",
        "failed",
        "cancelled",
    ):
        assert not can_transition(terminal, target)


def test_job_cannot_skip_directly_from_queued_to_completed() -> None:
    assert not can_transition("queued", "completed")
    assert not is_terminal("queued")

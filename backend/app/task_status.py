"""Task statuses (docs/SPEC.md §8B) and the ONE place that says which status changes are valid."""

from __future__ import annotations

QUEUED = "QUEUED"
ASSIGNED = "ASSIGNED"
RUNNING = "RUNNING"
WAITING_APPROVAL = "WAITING_APPROVAL"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

STATUSES = (QUEUED, ASSIGNED, RUNNING, WAITING_APPROVAL, SUCCEEDED, FAILED, CANCELLED)
TERMINAL = frozenset({SUCCEEDED, FAILED, CANCELLED})
ACTIVE = frozenset(STATUSES) - TERMINAL

# from → the statuses it may change to. A finished task never changes again.
TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({ASSIGNED, FAILED, CANCELLED}),
    ASSIGNED: frozenset({RUNNING, FAILED, CANCELLED}),
    # RUNNING → QUEUED happens only when a restart interrupted the task (crash recovery).
    RUNNING: frozenset({WAITING_APPROVAL, SUCCEEDED, FAILED, CANCELLED, QUEUED}),
    WAITING_APPROVAL: frozenset({RUNNING, FAILED, CANCELLED}),  # approved / rejected / cancelled
    SUCCEEDED: frozenset(),
    FAILED: frozenset(),
    CANCELLED: frozenset(),
}


class InvalidTransition(ValueError):
    def __init__(self, current: str, new: str) -> None:
        super().__init__(f"A task cannot go from {current} to {new}")
        self.current = current
        self.new = new


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, frozenset())


def ensure_transition(current: str, new: str) -> None:
    if not can_transition(current, new):
        raise InvalidTransition(current, new)

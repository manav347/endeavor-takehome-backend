import pytest

from src.app.models import EmailIn, EmailInternal
from src.app.scheduler import DependencyScheduler


def _build_internal(email_id: str, deadline: float, deps: list[str]):
    raw = EmailIn(
        email_id=email_id,
        subject=email_id,
        body='',
        deadline=deadline,
        dependencies=deps,
    )
    return EmailInternal.from_external(raw, fetch_start_ns=0)


def test_scheduler_order_and_heap():
    """Scheduler should pop earliest deadline among ready emails and respect deps."""
    a = _build_internal('A', 1.0, [])
    b = _build_internal('B', 2.0, ['A'])
    c = _build_internal('C', 1.5, ['A'])

    sched = DependencyScheduler([a, b, c])

    # Initially only A is ready
    batch = sched.get_ready_batch(1)
    assert [e.email_id for e in batch] == ['A']

    # Mark A done, now C and B become ready (C earlier deadline)
    sched.mark_done('A')
    batch = sched.get_ready_batch(2)
    assert [e.email_id for e in batch] == ['C', 'B']


def test_scheduler_cycle_detection():
    """DependencyScheduler should raise on cyclic graph."""
    x = _build_internal('X', 1.0, ['Y'])
    y = _build_internal('Y', 1.0, ['X'])
    with pytest.raises(ValueError):
        DependencyScheduler([x, y]) 
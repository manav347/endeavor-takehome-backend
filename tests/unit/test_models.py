import time

from src.app.models import EmailIn, EmailInternal


def test_emailin_dependency_parsing():
    """Comma-separated dependency string should parse into list."""
    raw = {
        'email_id': '123',
        'subject': 'Hello',
        'body': 'World',
        'deadline': 2.0,
        'dependencies': 'a, b , c'
    }
    email = EmailIn(**raw)
    assert email.dependencies == ['a', 'b', 'c']


def test_emailinternal_deadline_ns():
    """deadline_ns must equal fetch_start_ns + deadline (seconds) converted to ns."""
    raw = EmailIn(
        email_id='e1',
        subject='S',
        body='B',
        deadline=1.5,
        dependencies=[]
    )
    fetch_start_ns = 1_000_000_000  # arbitrary epoch
    internal = EmailInternal.from_external(raw, fetch_start_ns)
    expected_deadline = fetch_start_ns + int(1.5 * 1e9)
    assert internal.deadline_ns == expected_deadline 
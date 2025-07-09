import asyncio
from types import SimpleNamespace

import pytest
import httpx

from src.app.sink import ResponseSink
from src.app.client import EmailClient


class DummyClient(EmailClient):
    """EmailClient stub that simulates configurable response behaviour."""

    def __init__(self, behaviour):
        # behaviour: list of status codes to return sequentially
        self.behaviour = behaviour
        self.calls = 0

    async def post_response(self, payload: dict):
        code = self.behaviour[self.calls]
        self.calls += 1
        if 200 <= code < 300:
            return {}
        # Build HTTPStatusError similar to httpx raise_for_status
        request = httpx.Request('POST', 'http://example.com')
        response = httpx.Response(code, request=request)
        raise httpx.HTTPStatusError(f"Error {code}", request=request, response=response)


@pytest.mark.asyncio
async def test_sink_retries_success_after_failures():
    client = DummyClient([500, 502, 200])  # two 5xx then success
    sink = ResponseSink(client, max_retries=5)
    payload = {'email_id': 'x'}
    await sink.send(payload)
    assert sink.success_count == 1
    assert sink.retry_count == 2
    assert sink.failure_count == 0


@pytest.mark.asyncio
async def test_sink_gives_up_after_max_retries():
    client = DummyClient([500, 500, 500])  # always 5xx
    sink = ResponseSink(client, max_retries=2)  # only 2 retries allowed
    payload = {'email_id': 'y'}
    await sink.send(payload)
    assert sink.success_count == 0
    assert sink.retry_count == 2
    assert sink.failure_count == 1 
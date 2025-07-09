import asyncio
import importlib
from contextlib import asynccontextmanager

import pytest
import httpx

from src.app import main as main_module


@pytest.fixture(autouse=True)
def reload_app(monkeypatch):
    """Ensure fresh module state (e.g., _RUN_STATUS) for each test."""
    importlib.reload(main_module)
    yield
    importlib.reload(main_module)


@pytest.mark.asyncio
async def test_end_to_end_processing(monkeypatch):
    """End-to-end flow: ensure dependency order A -> (C before B)."""
    # ------------------------------------------------------------------
    # 1. Prepare fixture emails
    # ------------------------------------------------------------------
    emails_fixture = [
        {
            'email_id': 'A',
            'subject': 'S1',
            'body': 'B1',
            'deadline': 1.0,
            'dependencies': ''
        },
        {
            'email_id': 'B',
            'subject': 'S2',
            'body': 'B2',
            'deadline': 2.0,
            'dependencies': 'A'
        },
        {
            'email_id': 'C',
            'subject': 'S3',
            'body': 'B3',
            'deadline': 1.5,
            'dependencies': 'A'
        },
    ]

    # Capture POST order
    posted_ids: list[str] = []

    # Patch EmailClient.fetch_emails to return fixture
    def fake_fetch(self):  # noqa: D401
        return emails_fixture

    async def fake_post(self, payload):  # noqa: D401
        posted_ids.append(payload['email_id'])
        return {}

    monkeypatch.setattr('src.app.client.EmailClient.fetch_emails', fake_fetch)
    monkeypatch.setattr('src.app.client.EmailClient.post_response', fake_post)

    # Patch responder mock to speed up
    async def fast_llm(subject, body):
        return 'OK'

    monkeypatch.setattr('src.app.responder.mock_openai_response', fast_llm)
    monkeypatch.setattr('asyncio.sleep', lambda *_args, **_kw: asyncio.sleep(0))

    # Limit concurrency to 1 for deterministic order
    from src.app.config import settings
    original_workers = settings.concurrency_limit
    settings.concurrency_limit = 1

    # ------------------------------------------------------------------
    # 2. Spin up ASGI test client
    # ------------------------------------------------------------------
    async with httpx.AsyncClient(app=main_module.app, base_url='http://test') as ac:
        resp = await ac.post('/trigger?test=true')
        run_id = resp.json()['run_id']

        # Poll until state is completed (with reasonable timeout)
        for _ in range(50):
            status_resp = await ac.get(f'/status/{run_id}')
            if status_resp.json()['state'] != 'running':
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail('Run did not complete in time')

    # ------------------------------------------------------------------
    # 3. Assertions
    # ------------------------------------------------------------------
    assert posted_ids == ['A', 'C', 'B']

    # Restore setting
    settings.concurrency_limit = original_workers 
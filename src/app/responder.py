from __future__ import annotations

import asyncio
import random
import time
from typing import List

import numpy as np

from .models import EmailInternal, EmailOut
from .config import settings
from .sink import ResponseSink
from .scheduler import DependencyScheduler
from .client import EmailClient

# ---------------------------------------------------------------------------
# Mock LLM response helper
# ---------------------------------------------------------------------------

_response_counter = 0
_counter_lock = asyncio.Lock()


async def mock_openai_response(subject: str, body: str) -> str:  # noqa: D401
    """Simulate an LLM call with bounded exponential delay.

    Returns a canned response rotated from ``settings.mock_responses``.
    """

    # Artificial think-time (bounded 0.4–0.6 s)
    delay = float(
        np.clip(
            np.random.exponential(scale=settings.llm_delay_scale),
            settings.llm_delay_min,
            settings.llm_delay_max,
        )
    )
    await asyncio.sleep(delay)

    global _response_counter
    async with _counter_lock:
        text = settings.mock_responses[_response_counter % len(settings.mock_responses)]
        _response_counter += 1
    return f"Re: {subject}\n\n{text}"


# ---------------------------------------------------------------------------
# Orchestrator – EmailProcessor
# ---------------------------------------------------------------------------

class EmailProcessor:
    """Coordinates fetching, scheduling, and responding to emails."""

    def __init__(
        self,
        client: EmailClient,
        scheduler: DependencyScheduler,
        sink: ResponseSink,
    ) -> None:
        self._client = client
        self._scheduler = scheduler
        self._sink = sink
        self._sched_lock = asyncio.Lock()

    async def _process_loop(self) -> None:
        """Worker loop: pop emails, generate response, post, mark done."""
        while True:
            # --- fetch next ready email atomically and check work status
            async with self._sched_lock:
                email = self._scheduler.pop_next()
                if email is None:
                    # No available work; check if global queue empty (inside lock to avoid race)
                    if not self._scheduler.has_work():
                        break
                    # If queue empty but tasks still pending dependencies, yield briefly
                    # Release lock before sleeping to allow other workers to make progress
                    pass  # Will continue and sleep outside lock
            
            if email is None:
                # No work available right now, but dependencies might unlock more work
                await asyncio.sleep(0.01)
                continue

            # -------------------------------------------------------------
            # Timing logic – aim to land inside LLM delay window
            # -------------------------------------------------------------
            now_ns = time.time_ns()
            ahead_sec = email.deadline_ns / 1e9 - now_ns / 1e9 - 0.5  # 0.5 s before deadline
            if ahead_sec > 0:
                await asyncio.sleep(ahead_sec)

            # -------------------------------------------------------------
            # Generate response (mock LLM) & send
            # -------------------------------------------------------------
            response_text = await mock_openai_response(email.subject, email.body)
            payload = EmailOut(
                email_id=email.email_id,
                response_body=response_text,
                api_key=settings.api_key,
                test_mode="true" if settings.test_mode else None,
            )
            await self._sink.send(payload.dict(exclude_none=True))

            # Ensure 100 µs spacing *before* dependents are released
            await asyncio.sleep(settings.inter_dependency_gap)

            # -------------------------------------------------------------
            # Mark completion so dependents are enqueued *after* the gap
            # -------------------------------------------------------------
            async with self._sched_lock:
                self._scheduler.mark_done(email.email_id)

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    async def run(self, workers: int | None = None) -> None:
        """Launch *workers* concurrent process loops until all emails handled."""
        if workers is None:
            workers = settings.concurrency_limit
        async with asyncio.TaskGroup() as tg:  # Requires Python 3.11+
            for _ in range(workers):
                tg.create_task(self._process_loop()) 
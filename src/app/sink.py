from __future__ import annotations

import asyncio
from typing import Any

import logging
import random

from httpx import HTTPStatusError

from .client import EmailClient
from .config import settings


class ResponseSink:
    """Handle POSTing responses with retry/back-off and basic metrics."""

    def __init__(self, client: EmailClient, max_retries: int | None = None):
        self._client = client
        self._max_retries = max_retries or settings.max_retries

        # Metrics counters
        self.success_count: int = 0
        self.failure_count: int = 0
        self.retry_count: int = 0

        self._log = logging.getLogger(__name__ + ".ResponseSink")

    async def send(self, payload: dict[str, Any]) -> None:
        """POST payload with exponential back-off and jitter.

        On HTTP 5xx → retry with back-off (up to max_retries).
        On HTTP 4xx → log & count failure, do **not** retry.
        """

        delay = 0.2  # base backoff seconds

        for attempt in range(1, self._max_retries + 1):
            try:
                await self._client.post_response(payload)
                self.success_count += 1
                return
            except HTTPStatusError as exc:  # pragma: no cover
                status = exc.response.status_code

                if 400 <= status < 500:
                    # Client error – likely malformed payload or bad key.
                    self.failure_count += 1
                    self._log.error(
                        "4xx response (%s) for email_id=%s; dropping.",
                        status,
                        payload.get("email_id"),
                    )
                    return  # drop without retry

                # 5xx: server error – retry with back-off if attempts remain
                self._log.warning(
                    "5xx response (%s) on attempt %d/%d for email_id=%s",
                    status,
                    attempt,
                    self._max_retries,
                    payload.get("email_id"),
                )

                if attempt >= self._max_retries:
                    self.failure_count += 1
                    return

                # compute jittered delay
                jitter_factor = random.uniform(0.8, 1.2)
                await asyncio.sleep(delay * jitter_factor)
                self.retry_count += 1
                delay *= 2  # exponential growth

        # Should not reach – loop exits via return. 
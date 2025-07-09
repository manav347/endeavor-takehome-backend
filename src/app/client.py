from __future__ import annotations

from typing import Any, List

import httpx

from .config import settings


class EmailClient:
    """Thin wrapper around a shared ``httpx.AsyncClient`` instance.

    The actual HTTP client is created during FastAPI *startup* and injected
    here, avoiding the overhead of repeated connection pools.
    """

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    async def fetch_emails(self) -> List[Any]:
        """Retrieve emails from the external service and return raw JSON."""

        params = {"api_key": settings.api_key}
        if settings.test_mode:
            params["test_mode"] = "true"

        resp = await self._client.get(str(settings.emails_url), params=params)
        resp.raise_for_status()
        return resp.json()

    async def post_response(self, payload: dict[str, Any]) -> Any:
        """Submit a single email response payload."""

        resp = await self._client.post(str(settings.respond_url), json=payload)
        resp.raise_for_status()
        return resp.json() 
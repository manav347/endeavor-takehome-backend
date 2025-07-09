from __future__ import annotations

import asyncio
import logging
import time
from typing import List

from fastapi import FastAPI
import httpx

from .config import settings
from .client import EmailClient
from .models import EmailIn, EmailInternal
from .scheduler import DependencyScheduler
from .sink import ResponseSink
from .responder import EmailProcessor

app = FastAPI(title="Email Response System")

# Store run state in module-level variable for /status endpoint
_RUN_STATUS: dict[str, str] = {}

# Will hold the shared HTTPX client
_HTTP_CLIENT: httpx.AsyncClient | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout))


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        await _HTTP_CLIENT.aclose()
        _HTTP_CLIENT = None


@app.post("/trigger")
async def trigger(test: bool = False) -> dict[str, str]:
    """Fetch emails and start background task to process them."""

    run_id = str(int(time.time() * 1000))
    _RUN_STATUS[run_id] = "running"

    asyncio.create_task(_process_emails(run_id, test))
    return {"run_id": run_id}


@app.get("/status/{run_id}")
async def status(run_id: str) -> dict[str, str]:
    """Get the status of a processing run.
    
    Possible states:
    - running: Processing is in progress
    - completed: All emails processed successfully
    - failed: Processing failed due to an error
    - unknown: Run ID not found
    """
    return {"run_id": run_id, "state": _RUN_STATUS.get(run_id, "unknown")}


# ------------------------------------------------------------------
# Internal Helpers
# ------------------------------------------------------------------


async def _process_emails(run_id: str, test: bool) -> None:
    """Process emails with comprehensive error handling and status updates."""
    logger = logging.getLogger(__name__)
    
    try:
        settings.test_mode = test  # runtime override per run
        logger.info(f"Starting email processing run {run_id} (test_mode={test})")

        global _HTTP_CLIENT
        if _HTTP_CLIENT is None:
            # Shouldn't happen, but guard for safety
            _HTTP_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout))
            logger.warning("HTTP client was None, created new client in background task")

        client = EmailClient(_HTTP_CLIENT)

        # Step 1: Fetch emails with network error handling
        try:
            raw_emails = await client.fetch_emails()
            logger.info(f"Fetched {len(raw_emails)} emails from external API")
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch emails: {e}")
            _RUN_STATUS[run_id] = "failed"
            return
        except Exception as e:
            logger.error(f"Unexpected error fetching emails: {e}")
            _RUN_STATUS[run_id] = "failed"
            return

        # Step 2: Parse and validate emails
        try:
            fetch_start_ns = time.time_ns()
            emails: List[EmailInternal] = []
            
            for i, raw in enumerate(raw_emails):
                try:
                    email_in = EmailIn(**raw)
                    email_internal = EmailInternal.from_external(email_in, fetch_start_ns)
                    emails.append(email_internal)
                except Exception as e:
                    logger.error(f"Failed to parse email {i}: {e}. Raw data: {raw}")
                    # Continue with other emails rather than failing entire run
                    continue
            
            if not emails:
                logger.error("No valid emails after parsing")
                _RUN_STATUS[run_id] = "failed"
                return
                
            logger.info(f"Successfully parsed {len(emails)} emails")
            
        except Exception as e:
            logger.error(f"Unexpected error during email parsing: {e}")
            _RUN_STATUS[run_id] = "failed"
            return

        # Step 3: Build dependency scheduler with cycle detection
        try:
            scheduler = DependencyScheduler(emails)
            logger.info("Dependency scheduler created successfully")
        except ValueError as e:
            logger.error(f"Dependency validation failed: {e}")
            _RUN_STATUS[run_id] = "failed"
            return
        except Exception as e:
            logger.error(f"Unexpected error creating scheduler: {e}")
            _RUN_STATUS[run_id] = "failed"
            return

        # Step 4: Create sink and processor
        try:
            sink = ResponseSink(client)
            processor = EmailProcessor(client, scheduler, sink)
            logger.info("Email processor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize email processor: {e}")
            _RUN_STATUS[run_id] = "failed"
            return

        # Step 5: Run email processing
        try:
            await processor.run()
            logger.info(f"Email processing completed successfully. Success: {sink.success_count}, "
                       f"Failures: {sink.failure_count}, Retries: {sink.retry_count}")
            _RUN_STATUS[run_id] = "completed"
        except Exception as e:
            logger.error(f"Email processing failed: {e}")
            _RUN_STATUS[run_id] = "failed"
            return

    except Exception as e:
        # Catch-all for any unexpected errors
        logger.error(f"Unexpected error in _process_emails: {e}")
        _RUN_STATUS[run_id] = "failed" 
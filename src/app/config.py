from __future__ import annotations

from typing import List, Optional

from pydantic import HttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central application configuration loaded from environment variables.

    Environment variables use the prefix `APP_`, e.g. ``APP_API_KEY``.
    ``.env`` file in project root is also supported.
    """

    # Core credentials / endpoints
    api_key: str = "mpatel0708"
    emails_url: HttpUrl = "https://9uc4obe1q1.execute-api.us-east-2.amazonaws.com/dev/emails"
    respond_url: HttpUrl = "https://9uc4obe1q1.execute-api.us-east-2.amazonaws.com/dev/responses"

    # Behaviour flags
    test_mode: bool = True

    # Mock response pool (can be overridden via env)
    mock_responses: List[str] = [
        "Thank you for your email. I will get back to you shortly.",
        "I appreciate your message, and I'll respond as soon as possible.",
        "Your inquiry has been received. I'll review it and reply soon.",
        "Thanks for reaching out. Expect a detailed response shortly.",
    ]

    # Timing / retry tuning
    request_timeout: float = 10.0  # seconds
    max_retries: int = 3
    concurrency_limit: int = 10  # Max simultaneous email processing tasks

    # LLM mock delay parameters
    llm_delay_scale: float = 0.5  # mean of exponential distribution
    llm_delay_min: float = 0.4
    llm_delay_max: float = 0.6

    # Dependency response spacing (seconds)
    inter_dependency_gap: float = 1e-4  # 100 micro-seconds

    # Bonus: real OpenAI key
    openai_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        allow_mutation = True  # allow runtime overrides like /trigger?test=true


settings = Settings()  # singleton instance 
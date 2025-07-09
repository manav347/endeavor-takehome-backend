from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field, field_validator
import time


class EmailIn(BaseModel):
    """Raw email object as received from the GET endpoint."""

    email_id: str
    subject: str
    body: str
    deadline: float  # seconds relative to fetch time
    dependencies: List[str] = Field(default_factory=list)

    # Convert comma-separated string to list[str] when raw JSON provides a str.
    @field_validator("dependencies", mode="before")
    def _parse_deps(cls, v):  # noqa: D401, N805
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [d.strip() for d in v.split(",") if d.strip()]
        return v


class EmailInternal(EmailIn):
    """Enriched representation that includes an absolute nanosecond deadline."""

    deadline_ns: int  # time.time_ns() when the response is due

    @classmethod
    def from_external(cls, raw: "EmailIn", fetch_start_ns: int) -> "EmailInternal":
        return cls(
            **raw.dict(),
            deadline_ns=fetch_start_ns + int(raw.deadline * 1_000_000_000),
        )


class EmailOut(BaseModel):
    """Payload format required by the POST endpoint (spec-compliant)."""

    email_id: str
    response_body: str  # matches spec field name
    api_key: str
    test_mode: str | None = None 
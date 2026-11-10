"""Shared HTTP plumbing for Gnani APIs: auth header, retries, error mapping.

The API key is only ever placed in the outgoing request header. It is never
logged, never included in exception messages and never returned to clients.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger("ruko.gnani")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class GnaniError(Exception):
    service: str  # "prisma" | "timbre"
    status: int | None
    code: str
    message: str

    def __str__(self) -> str:  # safe for logs / clients: contains no secrets
        return f"{self.service} error {self.status or '-'} {self.code}: {self.message}"


def parse_error(service: str, resp: httpx.Response) -> GnaniError:
    """Map the documented Gnani error shapes onto GnaniError."""
    code, message = "HTTP_ERROR", resp.reason_phrase or "request failed"
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        if isinstance(body.get("error"), dict):  # STT envelope
            code = body["error"].get("type", code)
            message = body["error"].get("message", message)
        elif isinstance(body.get("detail"), dict):  # 401/402/403/429
            code = body["detail"].get("error_code", code)
            message = body["detail"].get("message", message)
        elif isinstance(body.get("detail"), list):  # 422 validation
            code, message = "VALIDATION_ERROR", str(body["detail"])[:300]
        elif "message" in body:  # TTS flat error
            message = str(body["message"])
            code = str(body.get("code", code))
        elif "code" in body:  # 504 UPSTREAM_TIMEOUT
            code = str(body["code"])
    if resp.status_code == 402 and code == "HTTP_ERROR":
        code = "INSUFFICIENT_CREDIT"
    return GnaniError(service, resp.status_code, code, message)


async def post_with_retry(
    client: httpx.AsyncClient,
    service: str,
    url: str,
    *,
    attempts: int = 3,
    base_delay: float = 0.6,
    **kwargs,
) -> httpx.Response:
    """POST with exponential backoff on connection errors and 429/5xx (per Gnani docs)."""
    last: GnaniError | None = None
    for i in range(attempts):
        try:
            resp = await client.post(url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = GnaniError(service, None, "NETWORK_ERROR", type(e).__name__)
        else:
            if resp.status_code < 400:
                return resp
            last = parse_error(service, resp)
            if resp.status_code not in RETRYABLE_STATUS:
                raise last
        log.warning("%s attempt %d/%d failed: %s", service, i + 1, attempts, last)
        if i < attempts - 1:
            await asyncio.sleep(base_delay * (2**i))
    assert last is not None
    raise last

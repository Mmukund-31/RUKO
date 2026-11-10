"""Gnani Prisma realtime STT client (WSS /stt/v3/stream).

Docs: https://docs.gnani.ai/api/STT/stt-websocket — verified live on 10 Nov 2026:
handshake headers below, raw PCM s16le mono frames of exactly 1024 bytes
(512 samples) at real-time cadence, server sends one FINAL `transcript`
message per VAD-closed segment (no partial transcripts are documented).
Reuses the same API key and base URL as the REST adapter.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

import websockets

from .http import GnaniError
from .prisma import KEYTERMS, LANG_HINTS

FRAME_BYTES = 1024  # 512 samples of 16-bit PCM — required frame size


class StreamConn(Protocol):
    async def send(self, data: bytes | str) -> None: ...
    async def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


class PrismaStream:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        fmt: str,
        language: str = "auto",
        sample_rate: int = 16000,
        idle_timeout_s: int = 900,
        connector: Any = None,
    ):
        self.url = base_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/stt/v3/stream"
        self.headers = {
            "x-api-key-id": api_key,
            "language_code": LANG_HINTS.get(language, "indic-auto"),
            "model": model,
            "format": fmt,
            "x-sample-rate": str(sample_rate),
            "x-idle-timeout-sec": str(idle_timeout_s),
            "keyterms": ",".join(KEYTERMS),
        }
        self._connector = connector or websockets.connect
        self._ws: StreamConn | None = None
        self._buf = bytearray()

    async def open(self) -> dict:
        try:
            self._ws = await self._connector(self.url, additional_headers=self.headers, max_size=2**22, open_timeout=10)
        except websockets.InvalidStatus as e:  # handshake rejected (401/402/429...)
            status = e.response.status_code
            code = {401: "INVALID_API_KEY", 402: "INSUFFICIENT_CREDIT", 403: "SCOPE_NOT_ALLOWED", 429: "RATE_LIMITED"}
            raise GnaniError("prisma-stream", status, code.get(status, "HANDSHAKE_FAILED"), "realtime STT handshake rejected")
        except (OSError, TimeoutError, websockets.WebSocketException) as e:
            raise GnaniError("prisma-stream", None, "NETWORK_ERROR", type(e).__name__)
        # first message is `connected` (or `error`, e.g. concurrent-session cap)
        first = json.loads(await self._recv_one())
        if first.get("type") == "error":
            await self.close()
            raise GnaniError("prisma-stream", None, "STREAM_REJECTED", str(first.get("message", ""))[:200])
        return first

    async def _recv_one(self) -> str:
        assert self._ws is not None
        async for msg in self._ws:
            if isinstance(msg, str):
                return msg
        raise GnaniError("prisma-stream", None, "CLOSED", "stream closed during handshake")

    async def send_pcm(self, pcm: bytes) -> None:
        """Buffer arbitrary-size PCM and forward exact 1024-byte frames."""
        assert self._ws is not None
        self._buf.extend(pcm)
        while len(self._buf) >= FRAME_BYTES:
            frame = bytes(self._buf[:FRAME_BYTES])
            del self._buf[:FRAME_BYTES]
            await self._ws.send(frame)

    async def commit(self) -> None:
        if self._ws is not None:
            await self._ws.send(json.dumps({"type": "commit"}))

    async def events(self) -> AsyncIterator[dict]:
        assert self._ws is not None
        async for msg in self._ws:
            if isinstance(msg, str):
                try:
                    yield json.loads(msg)
                except ValueError:
                    continue

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

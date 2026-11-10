"""Gnani Prisma speech-to-text adapter (REST, POST /stt/v3).

Docs: https://docs.gnani.ai/api/STT/speech-to-text
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .http import GnaniError, post_with_retry

STT_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}
ALLOWED_EXT = {"wav", "mp3", "ogg", "flac", "aac", "m4a"}

# App language choice -> Prisma language_code hint. Code-mixed choices pass a
# list so English words are kept (v3.0 treats lists as hints, not a lock).
LANG_HINTS = {
    "auto": "indic-auto",
    "te": "te-IN,en-IN",
    "hi": "hi-IN,en-IN",
    "hi-en": "hi-IN,en-IN",
    "en": "en-IN",
    "kn": "kn-IN,en-IN",
    "ta": "ta-IN,en-IN",
    "ml": "ml-IN,en-IN",
    "mr": "mr-IN,en-IN",
    "bn": "bn-IN,en-IN",
    "gu": "gu-IN,en-IN",
    "pa": "pa-IN,en-IN",
}

KEYTERMS = ["OTP", "Aadhaar", "PAN", "KYC", "UPI", "CVV", "PIN", "AnyDesk", "TeamViewer", "CBI", "RBI", "police"]


@dataclass
class Transcript:
    text: str
    detected_language: str | None
    model: str | None
    processing_time: float | None
    latency_s: float


class PrismaClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str, model: str, fmt: str):
        self._client = client
        self._url = base_url.rstrip("/") + "/stt/v3"
        self._key = api_key
        self._model = model
        self._format = fmt

    async def transcribe(
        self, audio: bytes, filename: str, language: str = "auto", previous_text: str | None = None
    ) -> Transcript:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXT:
            raise GnaniError("prisma", None, "UNSUPPORTED_AUDIO_FORMAT", f"extension '{ext}' not supported")
        if not audio:
            raise GnaniError("prisma", None, "EMPTY_AUDIO", "no audio received")
        data = {
            "model": self._model,
            "language_code": LANG_HINTS.get(language, "indic-auto"),
            "format": self._format,
            "keyterms": ",".join(KEYTERMS),
        }
        if previous_text:
            data["previous_text"] = previous_text[-600:]
        t0 = time.perf_counter()
        resp = await post_with_retry(
            self._client,
            "prisma",
            self._url,
            headers={"X-API-Key-ID": self._key},
            files={"audio_file": (f"speech.{ext}", audio, f"audio/{'mp4' if ext == 'm4a' else ext}")},
            data=data,
        )
        latency = time.perf_counter() - t0
        body = resp.json()
        if not body.get("success", True):
            err = body.get("error") or {}
            raise GnaniError("prisma", resp.status_code, err.get("type", "TRANSCRIPTION_FAILED"), err.get("message", ""))
        return Transcript(
            text=(body.get("transcript") or "").strip(),
            detected_language=body.get("detected_language_code"),
            model=body.get("model"),
            processing_time=body.get("processing_time"),
            latency_s=round(latency, 3),
        )

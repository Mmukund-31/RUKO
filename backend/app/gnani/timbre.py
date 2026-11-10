"""Gnani Timbre text-to-speech adapter (REST, POST /api/v1/tts/inference).

Docs: https://docs.gnani.ai/api/TTS/tts-inference
Returns raw MP3 bytes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .http import GnaniError, post_with_retry

# App language -> Timbre `language` value.
TTS_LANG = {
    "te": "te-IN",
    "hi": "hi-IN",
    "hi-en": "hi-en",
    "en": "en-IN",
    "kn": "kn-IN",
    "ta": "ta-IN",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "bn": "bn-IN",
    "gu": "gu-IN",
    "pa": "pa-IN",
}


@dataclass
class Speech:
    audio: bytes
    content_type: str
    latency_s: float


class TimbreClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str, model: str, voice: str, speed: float):
        self._client = client
        self._url = base_url.rstrip("/") + "/api/v1/tts/inference"
        self._key = api_key
        self._model = model
        self._voice = voice
        self._speed = speed

    async def synthesize(self, text: str, language: str, voice: str | None = None) -> Speech:
        text = text.strip()
        if not text:
            raise GnaniError("timbre", None, "EMPTY_TEXT", "nothing to speak")
        payload = {
            "text": text,
            "voice": voice or self._voice,
            "model": self._model,
            "language": TTS_LANG.get(language, "en-IN"),
            "speed": self._speed,
            "audio_config": {
                "sample_rate": 24000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "mp3",
                "bitrate": "64k",
            },
        }
        t0 = time.perf_counter()
        resp = await post_with_retry(
            self._client,
            "timbre",
            self._url,
            headers={"X-API-Key-ID": self._key, "Content-Type": "application/json"},
            json=payload,
        )
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:  # error body with 200 should not happen, but be safe
            raise GnaniError("timbre", resp.status_code, "UNEXPECTED_JSON", resp.text[:200])
        if not resp.content:
            raise GnaniError("timbre", resp.status_code, "EMPTY_AUDIO", "no audio returned")
        return Speech(resp.content, ctype or "audio/mpeg", round(time.perf_counter() - t0, 3))

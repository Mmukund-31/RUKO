"""Adapter tests against httpx.MockTransport (TEST MOCKS ONLY - never used by the app).

They pin the request shape to the documented Gnani API and check error mapping.
"""

import asyncio
import json

import httpx
import pytest

from app.gnani import GnaniError, PrismaClient, TimbreClient
from app.gnani import http as gh

KEY = "test-key-123"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def _s(_):
        return None

    monkeypatch.setattr(gh.asyncio, "sleep", _s)


def make(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_prisma_request_shape_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("X-API-Key-ID")
        seen["body"] = req.content
        return httpx.Response(
            200,
            json={"success": True, "transcript": "OTP అడుగుతున్నారు", "model": "prisma-v3.0",
                  "detected_language_code": "te-IN", "processing_time": 0.4},
        )

    async def go():
        async with make(handler) as c:
            p = PrismaClient(c, "https://api.vachana.ai", KEY, "prisma-v3.0", "codemix")
            return await p.transcribe(b"\x00\x01", "rec.m4a", "te", previous_text="hello")

    tr = asyncio.run(go())
    assert seen["url"] == "https://api.vachana.ai/stt/v3"
    assert seen["key"] == KEY
    body = seen["body"]
    for part in (b'name="audio_file"', b'filename="speech.m4a"', b"prisma-v3.0", b"codemix", b"te-IN,en-IN", b'name="previous_text"'):
        assert part in body
    assert tr.text == "OTP అడుగుతున్నారు" and tr.detected_language == "te-IN"


def test_prisma_auto_uses_indic_auto():
    def handler(req):
        assert b"indic-auto" in req.content
        return httpx.Response(200, json={"success": True, "transcript": ""})

    async def go():
        async with make(handler) as c:
            return await PrismaClient(c, "https://x", KEY, "prisma-v3.0", "codemix").transcribe(b"1", "a.wav")

    assert asyncio.run(go()).text == ""


def test_prisma_rejects_unknown_extension_and_empty_audio():
    async def go(data, name):
        async with make(lambda r: httpx.Response(200)) as c:
            await PrismaClient(c, "https://x", KEY, "m", "f").transcribe(data, name)

    with pytest.raises(GnaniError) as e:
        asyncio.run(go(b"1", "a.webm"))
    assert e.value.code == "UNSUPPORTED_AUDIO_FORMAT"
    with pytest.raises(GnaniError) as e:
        asyncio.run(go(b"", "a.wav"))
    assert e.value.code == "EMPTY_AUDIO"


def test_prisma_envelope_error_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(400, json={"success": False, "error": {"type": "MAX_AUDIO_DURATION_EXCEEDED", "message": "too long"}})

    async def go():
        async with make(handler) as c:
            await PrismaClient(c, "https://x", KEY, "m", "f").transcribe(b"1", "a.wav")

    with pytest.raises(GnaniError) as e:
        asyncio.run(go())
    assert e.value.code == "MAX_AUDIO_DURATION_EXCEEDED" and len(calls) == 1
    assert KEY not in str(e.value)


def test_rate_limit_is_retried_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"detail": {"error_code": "RATE_LIMITED", "message": "slow down"}})
        return httpx.Response(200, json={"success": True, "transcript": "ok"})

    async def go():
        async with make(handler) as c:
            return await PrismaClient(c, "https://x", KEY, "m", "f").transcribe(b"1", "a.wav")

    assert asyncio.run(go()).text == "ok" and len(calls) == 3


def test_auth_error_maps_detail_shape():
    def handler(req):
        return httpx.Response(401, json={"detail": {"error_code": "INVALID_API_KEY", "message": "bad key", "status_code": 401}})

    async def go():
        async with make(handler) as c:
            await TimbreClient(c, "https://x", KEY, "timbre-v3.0", "Lakshmi", 1.0).synthesize("hi", "en")

    with pytest.raises(GnaniError) as e:
        asyncio.run(go())
    assert e.value.code == "INVALID_API_KEY" and e.value.status == 401


def test_network_error_retried_then_raises():
    def handler(req):
        raise httpx.ConnectError("boom")

    async def go():
        async with make(handler) as c:
            await TimbreClient(c, "https://x", KEY, "m", "v", 1.0).synthesize("hi", "en")

    with pytest.raises(GnaniError) as e:
        asyncio.run(go())
    assert e.value.code == "NETWORK_ERROR"


def test_timbre_request_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["json"] = json.loads(req.content)
        seen["key"] = req.headers["X-API-Key-ID"]
        return httpx.Response(200, content=b"ID3fake-mp3", headers={"content-type": "audio/mpeg"})

    async def go():
        async with make(handler) as c:
            return await TimbreClient(c, "https://api.vachana.ai", KEY, "timbre-v3.0", "Lakshmi", 0.95).synthesize("నమస్కారం", "te")

    sp = asyncio.run(go())
    assert seen["url"] == "https://api.vachana.ai/api/v1/tts/inference"
    j = seen["json"]
    assert j["model"] == "timbre-v3.0" and j["voice"] == "Lakshmi" and j["language"] == "te-IN"
    assert j["audio_config"]["container"] == "mp3"
    assert sp.audio == b"ID3fake-mp3" and sp.content_type == "audio/mpeg"


def test_timbre_hinglish_maps_to_hi_en():
    def handler(req):
        assert json.loads(req.content)["language"] == "hi-en"
        return httpx.Response(200, content=b"x", headers={"content-type": "audio/mpeg"})

    async def go():
        async with make(handler) as c:
            await TimbreClient(c, "https://x", KEY, "m", "v", 1).synthesize("Theek hai", "hi-en")

    asyncio.run(go())

"""API tests. Gnani HTTP is replaced by httpx.MockTransport (TEST ONLY)."""

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import Services, create_app

KEY = "secret-test-key-xyz"


def gnani_mock(req: httpx.Request) -> httpx.Response:
    assert req.headers["X-API-Key-ID"] == KEY
    if req.url.path == "/stt/v3":
        return httpx.Response(200, json={"success": True, "transcript": "Caller is asking for my OTP",
                                         "detected_language_code": "en-IN", "model": "prisma-v3.0"})
    if req.url.path == "/api/v1/tts/inference":
        return httpx.Response(200, content=b"ID3mp3bytes", headers={"content-type": "audio/mpeg"})
    return httpx.Response(404)


def client(key: str | None = KEY, handler=gnani_mock) -> TestClient:
    settings = Settings(_env_file=None, gnani_api_key=SecretStr(key) if key else None)
    svc = Services(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return TestClient(create_app(svc))


def test_health_never_leaks_key():
    with client() as c:
        r = c.get("/health")
        assert r.json()["gnani_key_configured"] is True
        assert KEY not in r.text


def test_text_turn_returns_reply_and_audio():
    with client() as c:
        sid = c.post("/session").json()["session_id"]
        r = c.post("/turn/text", json={"session_id": sid, "text": "They want my OTP", "language": "auto"})
        assert r.status_code == 200
        j = r.json()
        assert j["risk"]["level"] == "HIGH_RISK" and j["done"]
        assert j["audio_url"].startswith("/audio/")
        audio = c.get(j["audio_url"])
        assert audio.content == b"ID3mp3bytes" and audio.headers["content-type"] == "audio/mpeg"
        assert KEY not in r.text


def test_voice_turn_uses_prisma_transcript():
    with client() as c:
        sid = c.post("/session").json()["session_id"]
        r = c.post("/turn/voice", data={"session_id": sid, "language": "auto"},
                   files={"audio": ("rec.m4a", b"fake-audio", "audio/mp4")})
        j = r.json()
        assert r.status_code == 200, j
        assert j["transcript"] == "Caller is asking for my OTP"
        assert j["detected_language"] == "en-IN"
        assert j["risk"]["level"] == "HIGH_RISK"


def test_tts_failure_still_returns_text():
    def handler(req):
        if req.url.path == "/api/v1/tts/inference":
            return httpx.Response(500, json={"success": False, "message": "We are facing technical difficulties."})
        return gnani_mock(req)

    with client(handler=handler) as c:
        sid = c.post("/session").json()["session_id"]
        j = c.post("/turn/text", json={"session_id": sid, "text": "KYC update call"}).json()
        assert j["audio_url"] is None and j["tts_error"]
        assert j["reply_text"]


def test_stt_error_maps_to_client_error():
    def handler(req):
        return httpx.Response(400, json={"success": False, "error": {"type": "EMPTY_AUDIO", "message": "empty"}})

    with client(handler=handler) as c:
        sid = c.post("/session").json()["session_id"]
        r = c.post("/turn/voice", data={"session_id": sid}, files={"audio": ("rec.m4a", b"x", "audio/mp4")})
        assert r.status_code == 400 and r.json()["error"]["code"] == "EMPTY_AUDIO"


def test_no_key_means_voice_unavailable_but_text_works():
    with client(key=None) as c:
        sid = c.post("/session").json()["session_id"]
        r = c.post("/turn/voice", data={"session_id": sid}, files={"audio": ("rec.m4a", b"x", "audio/mp4")})
        assert r.status_code == 503
        j = c.post("/turn/text", json={"session_id": sid, "text": "hello there caller"}).json()
        assert j["tts_error"] == "TTS_NOT_CONFIGURED"


def test_session_clear_and_expired_session():
    with client() as c:
        sid = c.post("/session").json()["session_id"]
        assert c.delete(f"/session/{sid}").json()["cleared"] is True
        r = c.post("/turn/text", json={"session_id": sid, "text": "hi"})
        assert r.status_code == 404


def test_rejects_unsupported_language_and_long_text():
    with client() as c:
        sid = c.post("/session").json()["session_id"]
        assert c.post("/turn/text", json={"session_id": sid, "text": "x", "language": "ur"}).status_code == 422
        assert c.post("/turn/text", json={"session_id": sid, "text": "x" * 900}).status_code == 422


def test_summary_texts_are_localized():
    with client() as c:
        sid = c.post("/session").json()["session_id"]
        j = c.post("/turn/text", json={"session_id": sid, "text": "వాళ్ళు OTP అడుగుతున్నారు"}).json()
        assert j["language"] == "te"
        assert j["risk"]["level_text"] and j["risk"]["action_text"]
        assert any("ఀ" <= ch <= "౿" for ch in j["risk"]["reason_text"])


def test_caller_lines_generated_once_and_cached(tmp_path):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return gnani_mock(req)

    settings = Settings(_env_file=None, gnani_api_key=SecretStr(KEY))
    svc = Services(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)), cache_dir=tmp_path)
    with TestClient(create_app(svc)) as c:
        assert c.get("/caller/A/0").content == b"ID3mp3bytes"
        assert c.get("/caller/a/0").status_code == 200
        assert calls.count("/api/v1/tts/inference") == 1
        assert len(list(tmp_path.glob("*.mp3"))) == 1  # cached on disk for the next run
        assert c.get("/caller/A/99").status_code == 404
        assert c.get("/caller/Z/0").status_code == 404
        sc = c.get("/scenarios").json()
        assert set(sc) == {"A", "B", "C", "D"} and len(sc["A"]["lines"]) == 5


def test_voice64_turn():
    import base64 as b64
    with client() as c:
        sid = c.post("/session").json()["session_id"]
        r = c.post("/turn/voice64", json={"session_id": sid, "audio_b64": b64.b64encode(b"fake").decode(), "ext": "m4a"})
        assert r.status_code == 200, r.text
        assert r.json()["transcript"] == "Caller is asking for my OTP"
        bad = c.post("/turn/voice64", json={"session_id": sid, "audio_b64": "@@not-base64@@"})
        assert bad.status_code == 400 and bad.json()["detail"]["code"] == "BAD_AUDIO_ENCODING"

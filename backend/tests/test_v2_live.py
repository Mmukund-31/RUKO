"""V2: signalling, caller-transcript aggregation, live alerts. Prisma stream is a TEST FAKE here."""

import asyncio
import json

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.conversation import Session
from app.conversation.manager import decide_alert, handle_caller_statement
from app.main import Services, create_app
from app.risk import Level

KEY = "secret-test-key-xyz"


def tts_mock(req: httpx.Request) -> httpx.Response:
    if req.url.path == "/api/v1/tts/inference":
        return httpx.Response(200, content=b"ID3alert", headers={"content-type": "audio/mpeg"})
    return httpx.Response(404)


class FakeStream:
    """Stands in for PrismaStream in tests only: emits scripted FINAL transcripts once audio arrives."""

    def __init__(self, finals):
        self.finals = finals
        self.received = bytearray()
        self.got_audio = asyncio.Event()

    async def open(self):
        return {"type": "connected"}

    async def send_pcm(self, pcm):
        self.received.extend(pcm)
        self.got_audio.set()

    async def events(self):
        await self.got_audio.wait()
        for f in self.finals:
            yield {"type": "transcript", "is_final": True, **f}
            await asyncio.sleep(0.01)
        await asyncio.sleep(3600)

    async def close(self):
        pass


def make_client(finals, streams):
    settings = Settings(_env_file=None, gnani_api_key=SecretStr(KEY))
    svc = Services(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(tts_mock)))

    def factory(language="auto"):
        st = FakeStream(finals)
        streams.append(st)
        return st

    svc.stream_factory = factory
    return TestClient(create_app(svc)), svc


# ---------------------------------------------------------------- signalling

def test_signalling_relays_between_two_peers_only():
    settings = Settings(_env_file=None)
    with TestClient(create_app(Services(settings))) as c:
        room = c.post("/rtc/room").json()
        assert len(room["room"]) == 6 and room["join_url"].endswith("/join/" + room["room"])
        with c.websocket_connect(f"/ws/signal/{room['room']}?role=user") as u:
            assert u.receive_json() == {"type": "joined", "room": room["room"], "role": "user", "peer": False}
            with c.websocket_connect(f"/ws/signal/{room['room']}?role=caller") as k:
                assert k.receive_json()["peer"] is True
                assert u.receive_json() == {"type": "peer-joined", "role": "caller"}
                assert k.receive_json() == {"type": "peer-joined", "role": "user"}
                u.send_text(json.dumps({"type": "offer", "sdp": "v=0..."}))
                assert k.receive_json() == {"type": "offer", "sdp": "v=0...", "from": "user"}
                k.send_text(json.dumps({"type": "answer", "sdp": "v=0 answer"}))
                assert u.receive_json()["type"] == "answer"
                k.send_text(json.dumps({"type": "ice", "candidate": {"candidate": "x"}}))
                assert u.receive_json()["candidate"] == {"candidate": "x"}
                k.send_text(json.dumps({"type": "not-allowed"}))  # dropped, not relayed
                k.send_text(json.dumps({"type": "bye"}))
                assert u.receive_json()["type"] == "bye"
            assert u.receive_json() == {"type": "peer-left", "role": "caller"}


def test_signalling_rejects_unknown_room():
    with TestClient(create_app(Services(Settings(_env_file=None)))) as c:
        with c.websocket_connect("/ws/signal/NOPE00?role=user") as ws:
            try:
                ws.receive_json()
                assert False, "should close"
            except Exception:
                pass


def test_rtc_config_and_qr():
    settings = Settings(_env_file=None, ice_turn_url="turn:turn.example:3478", ice_turn_username="u",
                        ice_turn_credential=SecretStr("p"))
    with TestClient(create_app(Services(settings))) as c:
        cfg = c.get("/rtc/config").json()
        assert cfg["turn"] is True and cfg["iceServers"][0]["urls"][0].startswith("stun:")
        assert cfg["iceServers"][1]["username"] == "u"
        svg = c.get("/qr", params={"data": "https://192.168.1.7:8443/join/ABCDEF"})
        assert svg.headers["content-type"] == "image/svg+xml" and b"<svg" in svg.content


# ---------------------------------------------------------------- evidence aggregation

def test_caller_statements_combine_across_turns():
    s = Session()
    o1 = handle_caller_statement(s, "Your bank account will be blocked today.", "en-IN", "seg-1", now=100)
    assert o1.risk.level is Level.SUSPICIOUS
    o2 = handle_caller_statement(s, "I am calling from the bank security department.", "en-IN", "seg-2", now=105)
    assert "authority" in o2.risk.signs and o2.risk.level is Level.SUSPICIOUS
    o3 = handle_caller_statement(s, "Tell me the OTP you received.", "en-IN", "seg-3", now=110)
    assert o3.risk.level is Level.HIGH
    assert {"otp", "threat", "urgency", "authority"} <= set(o3.risk.signs)
    ind = {i["indicator"]: i for i in s.facts.indicators()}
    assert ind["otp"]["severity"] == "critical" and ind["otp"]["strength"] == "direct"
    assert ind["otp"]["evidence"][0]["speaker"] == "CALLER" and ind["otp"]["evidence"][0]["ts"] == 110
    assert [t.speaker for t in s.transcripts] == ["CALLER"] * 3


def test_duplicate_segments_are_ignored():
    s = Session()
    assert handle_caller_statement(s, "Tell me the OTP", None, "seg-1", now=1) is not None
    assert handle_caller_statement(s, "Tell me the OTP", None, "seg-1", now=2) is None  # same segment
    assert handle_caller_statement(s, "Tell me the OTP", None, "seg-2", now=3) is None  # same text within 5 s
    assert handle_caller_statement(s, "   ", None, "seg-3", now=4) is None


def test_innocent_bank_enquiry_stays_insufficient():
    s = Session()
    for i, t in enumerate(["Hello, this is HDFC bank about your home loan application.",
                           "Please visit your nearest branch with your documents.",
                           "We will never ask for your OTP or PIN on a call."]):
        out = handle_caller_statement(s, t, "en-IN", f"s{i}", now=10 * i + 1)
    assert out.risk.level is Level.INSUFFICIENT
    assert decide_alert(s, out, now=100) == (None, None)


def test_digital_arrest_and_investment_and_kyc():
    s = Session()
    handle_caller_statement(s, "मैं क्राइम ब्रांच से इंस्पेक्टर बोल रहा हूँ।", "hi-IN", "a", now=1)
    o = handle_caller_statement(s, "आप डिजिटल अरेस्ट में हैं, तुरंत पैसे ट्रांसफर कीजिए।", "hi-IN", "b", now=5)
    assert o.risk.level is Level.HIGH and o.risk.scheme == "police"
    s = Session()
    o = handle_caller_statement(s, "Invest fifty thousand today and get guaranteed returns of double your money", "en-IN", "c", now=1)
    assert o.risk.level is Level.HIGH and o.risk.scheme == "investment"
    s = Session()
    o = handle_caller_statement(s, "Your KYC is pending, please update it.", "en-IN", "d", now=1)
    assert o.risk.level is Level.INSUFFICIENT
    o = handle_caller_statement(s, "Tell me your Aadhaar number and date of birth.", "en-IN", "e", now=5)
    assert o.risk.level is Level.SUSPICIOUS and "id_request" in o.risk.signs


def test_caller_context_answers_followups_so_they_are_not_asked():
    from app.conversation import handle_turn
    s = Session()
    handle_caller_statement(s, "Your card will be blocked, tell me the CVV and OTP.", "en-IN", "x", now=1)
    out = handle_turn(s, "what should I do?", "en")
    assert out.risk.level is Level.HIGH
    assert out.followup is None  # OTP/CVV already known from the caller transcript
    assert "Do not share any OTP" in out.reply


# ---------------------------------------------------------------- alert policy

def test_alert_throttle_and_dedupe():
    s = Session()
    o = handle_caller_statement(s, "Your account will be blocked today", "en-IN", "1", now=100)
    ind, text = decide_alert(s, o, now=100)
    assert ind == "threat" and "threatening" in text
    o = handle_caller_statement(s, "Your account will be blocked, I repeat", "en-IN", "2", now=103)
    assert decide_alert(s, o, now=103) == (None, None)  # already announced
    o = handle_caller_statement(s, "Tell me the OTP now", "en-IN", "3", now=105)
    ind, text = decide_alert(s, o, now=105)  # critical beats the 10 s cooldown after 4 s
    assert ind == "otp" and "Do not share it" in text and "high risk" in text
    o = handle_caller_statement(s, "Also send money by UPI", "en-IN", "4", now=107)
    assert decide_alert(s, o, now=107) == (None, None)  # cooldown; stays pending
    ind, _ = decide_alert(s, o, now=118)
    assert ind == "money"


def test_alert_language_follows_user_preference():
    s = Session()
    s.preferred_language = "te"
    o = handle_caller_statement(s, "Please tell me the OTP", "en-IN", "1", now=1)
    _, text = decide_alert(s, o, now=1)
    assert "OTP చెప్పకండి" in text


# ---------------------------------------------------------------- live socket end to end (fake stream)

def test_live_socket_transcribes_caller_audio_and_alerts():
    finals = [
        {"text": "I am calling from your bank security department.", "segment_id": "s1", "detected_language_code": "en-IN"},
        {"text": "I am calling from your bank security department.", "segment_id": "s1", "detected_language_code": "en-IN"},
        {"text": "Please tell me the OTP.", "segment_id": "s2", "detected_language_code": "en-IN"},
    ]
    streams = []
    client, svc = make_client(finals, streams)
    with client as c:
        sid = c.post("/session").json()["session_id"]
        with c.websocket_connect(f"/ws/live/{sid}?language=en") as ws:
            ws.send_bytes(b"\x00\x01" * 700)  # caller PCM
            got = []
            while not any(m["type"] == "alert" for m in got):
                got.append(ws.receive_json())
        kinds = [m["type"] for m in got]
        assert kinds.count("transcript") == 2  # duplicate segment dropped
        tr = [m for m in got if m["type"] == "transcript"]
        assert all(m["speaker"] == "CALLER" and m["final"] for m in tr)
        risk = [m for m in got if m["type"] == "risk"][-1]["risk"]
        assert risk["level"] == "HIGH_RISK" and risk["indicators"][0]["indicator"] == "otp"
        alert = [m for m in got if m["type"] == "alert"][0]
        assert alert["indicator"] == "otp" and alert["audio_url"].startswith("/audio/")
        assert c.get(alert["audio_url"]).content == b"ID3alert"
        assert len(streams[0].received) == 1400  # audio reached the (fake) Prisma stream
        log = c.get(f"/session/{sid}/transcript").json()["transcripts"]
        assert [t["speaker"] for t in log] == ["CALLER", "CALLER"]


def test_live_socket_silenced_voice_still_detects():
    finals = [{"text": "Tell me the OTP.", "segment_id": "s1"}]
    client, _ = make_client(finals, [])
    with client as c:
        sid = c.post("/session").json()["session_id"]
        with c.websocket_connect(f"/ws/live/{sid}?voice=false") as ws:
            ws.send_bytes(b"\x00" * 64)
            msgs = []
            while not any(m["type"] == "alert" for m in msgs):
                msgs.append(ws.receive_json())
        alert = [m for m in msgs if m["type"] == "alert"][0]
        assert alert["audio_url"] is None and "OTP" in alert["text"]
        assert any(m["type"] == "risk" and m["risk"]["level"] == "HIGH_RISK" for m in msgs)


def test_live_socket_without_key_reports_error():
    with TestClient(create_app(Services(Settings(_env_file=None)))) as c:
        sid = c.post("/session").json()["session_id"]
        with c.websocket_connect(f"/ws/live/{sid}") as ws:
            assert ws.receive_json() == {"type": "stt", "state": "error", "detail": "STT_NOT_CONFIGURED"}


def test_user_turns_logged_separately_from_caller():
    finals = [{"text": "Tell me the OTP.", "segment_id": "s1"}]
    client, _ = make_client(finals, [])
    with client as c:
        sid = c.post("/session").json()["session_id"]
        with c.websocket_connect(f"/ws/live/{sid}") as ws:
            ws.send_bytes(b"\x00" * 64)
            while ws.receive_json()["type"] != "alert":
                pass
        r = c.post("/turn/text", json={"session_id": sid, "text": "is this real?"}).json()
        assert r["risk"]["level"] == "HIGH_RISK"  # caller context used
        speakers = [t["speaker"] for t in c.get(f"/session/{sid}/transcript").json()["transcripts"]]
        assert speakers == ["CALLER", "USER"]


def test_caller_saying_we_sent_otp_is_not_a_user_loss():
    s = Session()
    o = handle_caller_statement(s, "We have sent an OTP to your mobile. Please tell me the OTP.", "en-IN", "1", now=1)
    assert not o.risk.loss_reported and o.risk.action == "no_otp"


def test_held_back_critical_alert_fires_without_another_caller_statement():
    finals = [
        {"text": "Your account will be blocked today.", "segment_id": "s1"},
        {"text": "Tell me the OTP.", "segment_id": "s2"},  # arrives inside the cooldown
    ]
    client, _ = make_client(finals, [])
    with client as c:
        sid = c.post("/session").json()["session_id"]
        with c.websocket_connect(f"/ws/live/{sid}") as ws:
            ws.send_bytes(b"\x00" * 64)
            alerts = []
            while len(alerts) < 2:
                m = ws.receive_json()
                if m["type"] == "alert":
                    alerts.append(m["indicator"])
        assert alerts == ["threat", "otp"]  # OTP spoken after the short critical cooldown, unprompted

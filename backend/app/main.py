"""RUKO backend: the only component that talks to Gnani (key stays here)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import segno
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .conversation import Session, TurnOutcome, handle_turn
from .conversation.responses import speech_language
from .gnani import GnaniError, PrismaClient, TimbreClient
from .gnani.prisma_stream import PrismaStream
from .live import live_socket
from .payloads import risk_dict
from .scenarios import SCENARIOS
from .sessions import AudioCache, SessionStore
from .signaling import Rooms, lan_ip, signal_socket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ruko")

MAX_AUDIO_BYTES = 6 * 1024 * 1024  # ~30 s of m4a is well under this
MAX_TEXT = 800
CALLER_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "caller"
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

Lang = Literal["auto", "te", "hi", "hi-en", "en", "kn", "ta", "ml", "mr", "bn", "gu", "pa"]


# ---------- models ----------
class RiskOut(BaseModel):
    level: str
    score: int
    signs: list[str]
    evidence: list[str]
    missing: list[str]
    main_reason: str | None
    action: str
    loss_reported: bool
    scheme: str
    level_text: str
    reason_text: str
    action_text: str
    indicators: list[dict] = []

class TurnOut(BaseModel):
    session_id: str
    reply_text: str
    language: str
    audio_url: str | None = None
    tts_error: str | None = None
    tts_latency_s: float | None = None
    risk: RiskOut
    followup: str | None
    done: bool
    transcript: str | None = None
    detected_language: str | None = None
    stt_latency_s: float | None = None

class TextTurnIn(BaseModel):
    session_id: str
    text: str = Field(max_length=MAX_TEXT)
    language: Lang = "auto"

class VoiceB64In(BaseModel):
    session_id: str
    language: Lang = "auto"
    ext: Literal["m4a", "wav", "mp3", "ogg", "aac", "flac"] = "m4a"
    audio_b64: str = Field(min_length=1, max_length=MAX_AUDIO_BYTES * 4 // 3 + 8)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    language: Lang = "en"


class Services:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None, cache_dir: Path | None = None):
        self.settings = settings
        self.cache_dir = cache_dir  # synthetic caller audio only; never user audio
        self.sessions = SessionStore()
        self.audio = AudioCache()
        self.http = http or httpx.AsyncClient(timeout=settings.http_timeout_s)
        self.caller_audio: dict[str, tuple[bytes, str]] = {}
        self.rooms = Rooms()
        self.stream_factory = None  # (language) -> PrismaStream ; None when no key
        self.prisma: PrismaClient | None = None
        self.timbre: TimbreClient | None = None
        if settings.key_configured:
            key = settings.gnani_api_key.get_secret_value()  # type: ignore[union-attr]
            self.prisma = PrismaClient(self.http, settings.gnani_base_url, key, settings.prisma_model, settings.prisma_format)
            self.timbre = TimbreClient(
                self.http, settings.gnani_base_url, key, settings.timbre_model, settings.timbre_voice, settings.timbre_speed
            )
            self.stream_factory = lambda language="auto": PrismaStream(
                settings.gnani_base_url, key, settings.prisma_model, settings.prisma_format, language
            )


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.svc = services or Services(get_settings(), cache_dir=CALLER_CACHE)
        if not app.state.svc.settings.key_configured:
            log.warning("GNANI_API_KEY is not set: voice input and spoken replies are unavailable")
        yield
        await app.state.svc.http.aclose()

    app = FastAPI(title="RUKO backend", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def svc(request: Request) -> Services:
        return request.app.state.svc

    @app.exception_handler(GnaniError)
    async def gnani_error(_: Request, e: GnaniError):
        log.warning("%s", e)
        status = 502 if (e.status or 500) >= 500 or e.status is None else 400
        if e.code in ("RATE_LIMITED",):
            status = 429
        return JSONResponse(status_code=status, content={"error": {"service": e.service, "code": e.code, "message": e.message}})

    # ---------- helpers ----------
    def get_session(s: Services, sid: str) -> Session:
        sess = s.sessions.get(sid)
        if not sess:
            raise HTTPException(404, detail={"code": "SESSION_NOT_FOUND", "message": "Session expired. Start again."})
        return sess

    async def speak(s: Services, text: str, lang: str) -> tuple[str | None, str | None, float | None]:
        if not s.timbre:
            return None, "TTS_NOT_CONFIGURED", None
        try:
            sp = await s.timbre.synthesize(text, speech_language(lang))
        except GnaniError as e:
            log.warning("%s", e)
            return None, e.code, None
        return f"/audio/{s.audio.put(sp.audio, sp.content_type)}", None, sp.latency_s

    async def build(s: Services, sess: Session, out: TurnOutcome, **extra) -> TurnOut:
        url, err, lat = await speak(s, out.reply, out.language)
        r = out.risk
        return TurnOut(
            session_id=sess.id,
            reply_text=out.reply,
            language=out.language,
            audio_url=url,
            tts_error=err,
            tts_latency_s=lat,
            risk=RiskOut(**risk_dict(out.language, r, sess.facts)),
            followup=out.followup,
            done=out.done,
            **extra,
        )

    # ---------- routes ----------
    @app.get("/health")
    async def health(request: Request):
        st = svc(request).settings
        return {
            "ok": True,
            "gnani_key_configured": st.key_configured,
            "prisma_model": st.prisma_model,
            "timbre_model": st.timbre_model,
            "timbre_voice": st.timbre_voice,
        }

    @app.post("/session")
    async def new_session(request: Request):
        return {"session_id": svc(request).sessions.create().id}

    @app.delete("/session/{sid}")
    async def end_session(sid: str, request: Request):
        return {"cleared": svc(request).sessions.delete(sid)}

    @app.post("/turn/text", response_model=TurnOut)
    async def text_turn(body: TextTurnIn, request: Request):
        s = svc(request)
        sess = get_session(s, body.session_id)
        out = handle_turn(sess, body.text, body.language, source="text")
        return await build(s, sess, out)

    async def voice(s: Services, sess: Session, data: bytes, filename: str, language: str) -> TurnOut:
        if not s.prisma:
            raise HTTPException(503, detail={"code": "STT_NOT_CONFIGURED", "message": "Gnani API key not configured on server."})
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(413, detail={"code": "AUDIO_TOO_LARGE", "message": "Recording too long (max 30 seconds)."})
        previous = " ".join(t.text for t in sess.history[-4:])
        tr = await s.prisma.transcribe(data, filename, language, previous_text=previous or None)
        # Raw audio is discarded here; only the transcript enters the session.
        out = handle_turn(sess, tr.text, language, stt_detected=tr.detected_language, source="voice")
        return await build(
            s, sess, out, transcript=tr.text, detected_language=tr.detected_language, stt_latency_s=tr.latency_s
        )

    @app.post("/turn/voice", response_model=TurnOut)
    async def voice_turn(
        request: Request,
        session_id: str = Form(...),
        language: Lang = Form("auto"),
        audio: UploadFile = File(...),
    ):
        s = svc(request)
        sess = get_session(s, session_id)
        return await voice(s, sess, await audio.read(), audio.filename or "speech.m4a", language)

    @app.post("/turn/voice64", response_model=TurnOut)
    async def voice_turn_b64(body: VoiceB64In, request: Request):
        """Same as /turn/voice, with the audio as base64 JSON (robust from React Native)."""
        s = svc(request)
        sess = get_session(s, body.session_id)
        try:
            data = base64.b64decode(body.audio_b64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, detail={"code": "BAD_AUDIO_ENCODING", "message": "Audio could not be decoded."})
        return await voice(s, sess, data, f"speech.{body.ext}", body.language)

    @app.post("/speak")
    async def speak_again(body: SpeakIn, request: Request):
        url, err, lat = await speak(svc(request), body.text, body.language)
        if err:
            raise HTTPException(502, detail={"code": err, "message": "Voice unavailable."})
        return {"audio_url": url, "tts_latency_s": lat}

    @app.get("/scenarios")
    async def scenarios():
        return {
            k: {**{f: v[f] for f in ("title", "caller", "number", "language")}, "lines": v["lines"]}
            for k, v in SCENARIOS.items()
        }

    @app.get("/caller/{scenario}/{index}")
    async def caller_line(scenario: str, index: int, request: Request):
        """One line of the synthetic caller's script, spoken by Timbre."""
        s = svc(request)
        sc = SCENARIOS.get(scenario.upper())
        if not sc or not 0 <= index < len(sc["lines"]):
            raise HTTPException(404, detail={"code": "UNKNOWN_SCENARIO", "message": "No such scenario line."})
        text = sc["lines"][index]
        key = hashlib.sha1(f"{sc['voice']}|{sc['language']}|{s.settings.timbre_model}|{text}".encode()).hexdigest()[:16]
        if key not in s.caller_audio:
            path = s.cache_dir / f"{key}.mp3" if s.cache_dir else None
            if path and path.exists():
                s.caller_audio[key] = (path.read_bytes(), "audio/mpeg")
            else:
                if not s.timbre:
                    raise HTTPException(503, detail={"code": "TTS_NOT_CONFIGURED", "message": "Gnani API key not configured."})
                sp = await s.timbre.synthesize(text, sc["language"], voice=sc["voice"])
                s.caller_audio[key] = (sp.audio, sp.content_type)
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(sp.audio)
        data, ctype = s.caller_audio[key]
        return Response(data, media_type=ctype, headers={"Cache-Control": "public, max-age=3600"})

    # ---------- V2: live call ----------
    @app.get("/rtc/config")
    async def rtc_config(request: Request):
        st = svc(request).settings
        servers: list[dict] = [{"urls": [u.strip() for u in st.ice_stun_urls.split(",") if u.strip()]}]
        if st.ice_turn_url:
            servers.append({
                "urls": [u.strip() for u in st.ice_turn_url.split(",")],
                "username": st.ice_turn_username or "",
                "credential": st.ice_turn_credential.get_secret_value() if st.ice_turn_credential else "",
            })
        return {"iceServers": servers, "turn": bool(st.ice_turn_url)}

    def join_base(request: Request) -> str:
        st = svc(request).settings
        if st.public_base_url:
            return st.public_base_url.rstrip("/")
        url = request.url
        host = url.hostname or "localhost"
        if host in ("localhost", "127.0.0.1", "::1"):
            host = lan_ip()
        port = f":{url.port}" if url.port else ""
        return f"{url.scheme}://{host}{port}"

    @app.post("/rtc/room")
    async def new_room(request: Request):
        room = svc(request).rooms.create()
        join = f"{join_base(request)}/join/{room.id}"
        return {"room": room.id, "join_url": join, "secure": join.startswith("https://")}

    @app.get("/qr")
    async def qr(data: str = Query(..., max_length=300)):
        buf = __import__("io").BytesIO()
        segno.make(data, error="m").save(buf, kind="svg", scale=6, border=2, dark="#0E1726")
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.websocket("/ws/signal/{room}")
    async def ws_signal(ws: WebSocket, room: str, role: str = "user"):
        await signal_socket(ws, ws.app.state.svc.rooms, room, role)

    @app.websocket("/ws/live/{sid}")
    async def ws_live(ws: WebSocket, sid: str, language: str = "auto", voice: bool = True):
        s = ws.app.state.svc
        sess = s.sessions.get(sid)
        if sess is not None:
            sess.preferred_language = language
            sess.voice_alerts = voice
        await live_socket(ws, s, sid)

    @app.get("/session/{sid}/transcript")
    async def transcript(sid: str, request: Request):
        sess = get_session(svc(request), sid)
        return {"transcripts": [
            {"speaker": t.speaker, "text": t.text, "ts": t.ts, "language": t.language, "final": t.final}
            for t in sess.transcripts
        ]}

    if WEB_DIR.exists():
        app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")

        @app.get("/")
        async def web_user():
            return FileResponse(WEB_DIR / "index.html")

        @app.get("/join/{room}")
        async def web_caller(room: str):
            return FileResponse(WEB_DIR / "caller.html")

    @app.get("/audio/{cid}")
    async def get_audio(cid: str, request: Request):
        clip = svc(request).audio.get(cid)
        if not clip:
            raise HTTPException(404, detail={"code": "AUDIO_EXPIRED", "message": "Audio expired."})
        return Response(clip.data, media_type=clip.content_type, headers={"Cache-Control": "no-store"})

    return app


app = create_app()

"""Live caller-audio relay: browser (remote WebRTC track, 16 kHz PCM) -> Prisma realtime.

WS /ws/live/<session_id>
  client -> server  binary: Int16 LE mono 16 kHz PCM of the CALLER (remote track only)
                    text:   {"type":"settings","language":"te","voice":true}
  server -> client  {"type":"stt","state":"connecting|connected|reconnecting|error","detail":...}
                    {"type":"transcript","speaker":"CALLER","text","ts","language","final":true}
                    {"type":"risk","risk":{...}}            (when evidence changes)
                    {"type":"alert","indicator","text","audio_url"|null,"language"}

Only FINAL transcripts are analysed (Prisma realtime sends finals only).
The user's own speech never comes through this socket; it uses /turn/voice64.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from .conversation.manager import alert_language, decide_alert, handle_caller_statement
from .conversation.responses import speech_language
from .gnani import GnaniError
from .gnani.prisma_stream import PrismaStream
from .payloads import risk_dict

if TYPE_CHECKING:
    from .main import Services

log = logging.getLogger("ruko.live")

QUEUE_FRAMES = 400  # ~6-13 s of audio; older audio is dropped if Prisma is unreachable
BACKOFF = (1, 2, 4, 8, 10)


async def live_socket(ws: WebSocket, svc: "Services", sid: str) -> None:
    await ws.accept()
    sess = svc.sessions.get(sid)
    if sess is None:
        await ws.close(code=4404, reason="session not found")
        return
    send_lock = asyncio.Lock()
    closed = asyncio.Event()
    audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=QUEUE_FRAMES)
    tts_tasks: set[asyncio.Task] = set()
    last: dict = {"out": None}

    async def send(msg: dict) -> None:
        async with send_lock:
            with contextlib.suppress(Exception):
                await ws.send_text(json.dumps(msg, ensure_ascii=False))

    async def speak_alert(indicator: str, text: str, lang: str) -> None:
        url = None
        if sess.voice_alerts and svc.timbre:
            try:
                sp = await svc.timbre.synthesize(text, speech_language(lang))
                url = f"/audio/{svc.audio.put(sp.audio, sp.content_type)}"
            except GnaniError as e:
                log.warning("alert TTS failed: %s", e)
        await send({"type": "alert", "indicator": indicator, "text": text, "audio_url": url, "language": lang})

    async def on_final(ev: dict) -> None:
        out = handle_caller_statement(
            sess, ev.get("text", ""), ev.get("detected_language_code"), ev.get("segment_id")
        )
        if out is None:
            return
        r = out.record
        await send({"type": "transcript", "speaker": "CALLER", "text": r.text, "ts": r.ts,
                    "language": r.language, "final": True, "segment_id": r.segment_id})
        lang = alert_language(sess, r.language)
        if out.newly or out.level_changed:
            await send({"type": "risk", "risk": risk_dict(lang, out.risk, sess.facts)})
        last["out"] = out
        maybe_alert(out)

    def maybe_alert(out) -> None:
        indicator, text = decide_alert(sess, out)
        if text:
            lang = alert_language(sess, out.record.language)
            t = asyncio.create_task(speak_alert(indicator, text, lang))  # don't stall the transcript stream
            tts_tasks.add(t)
            t.add_done_callback(tts_tasks.discard)

    async def alert_ticker() -> None:
        """A warning held back by the cooldown is spoken as soon as the cooldown ends,
        without waiting for the caller to say something else."""
        while not closed.is_set():
            await asyncio.sleep(1.0)
            if last["out"] is not None:
                maybe_alert(last["out"])

    async def upstream() -> None:
        attempt = 0
        if svc.stream_factory is None:
            await send({"type": "stt", "state": "error", "detail": "STT_NOT_CONFIGURED"})
            return
        while not closed.is_set():
            stream: PrismaStream = svc.stream_factory(sess.preferred_language)
            await send({"type": "stt", "state": "connecting" if attempt == 0 else "reconnecting"})
            try:
                await stream.open()
                attempt = 0
                await send({"type": "stt", "state": "connected"})

                async def pump() -> None:
                    while True:
                        await stream.send_pcm(await audio_q.get())

                pump_task = asyncio.create_task(pump())
                try:
                    async for ev in stream.events():
                        kind = ev.get("type")
                        if kind == "transcript" and ev.get("is_final", True):
                            await on_final(ev)
                        elif kind == "error":
                            log.warning("prisma stream error: %s", str(ev.get("message"))[:200])
                            await send({"type": "stt", "state": "error", "detail": str(ev.get("message", ""))[:160]})
                finally:
                    pump_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await pump_task
            except GnaniError as e:
                log.warning("%s", e)
                await send({"type": "stt", "state": "error", "detail": e.code})
                if e.code in ("INVALID_API_KEY", "INSUFFICIENT_CREDIT", "SCOPE_NOT_ALLOWED"):
                    return  # not recoverable by retrying
            except Exception as e:  # network drop, 15-min cap (1001), idle timeout...
                log.warning("prisma stream closed: %s", type(e).__name__)
            finally:
                await stream.close()
            if closed.is_set():
                break
            await asyncio.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
            attempt += 1

    up = asyncio.create_task(upstream())
    ticker = asyncio.create_task(alert_ticker())
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                data = msg["bytes"]
                if audio_q.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        audio_q.get_nowait()
                audio_q.put_nowait(data)
            elif msg.get("text"):
                try:
                    ctl = json.loads(msg["text"])
                except ValueError:
                    continue
                if ctl.get("type") == "settings":
                    if "voice" in ctl:
                        sess.voice_alerts = bool(ctl["voice"])
                    if ctl.get("language"):
                        sess.preferred_language = str(ctl["language"])
                    await send({"type": "settings", "voice": sess.voice_alerts, "language": sess.preferred_language})
    except WebSocketDisconnect:
        pass
    finally:
        closed.set()
        up.cancel()
        ticker.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await up
        for t in list(tts_tasks):
            t.cancel()
        sess.touched = time.time()

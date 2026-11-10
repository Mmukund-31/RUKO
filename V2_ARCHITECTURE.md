# RUKO V2 — Architecture

```
 CALLER device (phone Chrome)                RUKO USER device (laptop/phone Chrome, headphones)
 /join/<room>                                /  (RUKO live call page)
 ┌────────────────────┐   WebRTC audio (P2P, DTLS-SRTP)   ┌──────────────────────────────────────────┐
 │ mic ─► callTrack ──┼──────────────────────────────────►│ remote track ─► <audio id=caller> (hear) │
 │ <audio> ◄──────────┼◄──────────────────────────────────┼── callTrack (user mic #1)                │
 └─────────┬──────────┘                                   │      │ enabled=false in private mode      │
           │ WS /ws/signal/<room>?role=caller             │ remote track ─► AudioWorklet(16 kHz) ──┐ │
           ▼                                              │ private mic #2 ─► AudioWorklet ─► WAV  │ │
   ┌───────────────── FastAPI backend (holds Gnani key) ──┤ <audio id=ruko> ◄─ Timbre mp3 (local)  │ │
   │ signaling.py  relays offer/answer/ICE only           └────────┬──────────────┬────────────────┘ │
   │ live.py      WS /ws/live/<session>: CALLER PCM ◄──────────────┘(binary)      │ POST /turn/voice64│
   │   └► gnani/prisma_stream.py ─► wss://api.vachana.ai/stt/v3/stream (finals)   │ POST /turn/text   │
   │   └► transcript log [CALLER] ─► risk engine (evidence aggregation)           ▼                  │
   │   └► alert policy (dedupe/throttle) ─► gnani/timbre.py ─► /audio/<id> ─► WS event to user page   │
   │ main.py      /turn/* (USER) ─► Prisma REST ─► conversation manager (same session facts)         │
   └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 1. Three separate audio paths
| Path | Source | Goes to | Never goes to |
|---|---|---|---|
| **Caller audio** | the WebRTC remote track | the user's headphones (`<audio id=caller>`) and an AudioWorklet → `/ws/live` → Prisma realtime | — |
| **User call mic** (`callTrack`, getUserMedia #1) | the user's mic | the RTCPeerConnection sender only | Prisma |
| **Private RUKO mic** (getUserMedia #2, a separate track) | the user's mic | AudioWorklet → WAV → `/turn/voice64` → Prisma REST | **the peer connection** (it is never added to a sender) |
| **RUKO voice** (Timbre mp3) | backend `/audio/<id>` | `<audio id=ruko>`, local output only | **the peer connection** (it is not a MediaStream track at all) |

Private mode: `callTrack.enabled = false` (the caller receives silence, the connection stays up), mic #2 opens, and the caller audio stays playing (ducked). On **Back to call** the user explicitly re-enables `callTrack`, and mic #2 is stopped.
While RUKO speaks an alert outside private mode, `callTrack` is paused and restored automatically after playback. This limits acoustic leakage when the user isn't wearing headphones. The page warns if no headphone-like output device is detected. **Acoustic privacy is only guaranteed with headphones.**
`window.__ruko.isolation()` reports the tracks on every sender. The E2E test checks that it contains only `callTrack`, and measures the caller-side inbound audio energy while the user is in private mode and RUKO is speaking.

## 2. Signalling (`backend/app/signaling.py`)
- `POST /rtc/room` → `{room, join_url}`. A room has at most one `user` and one `caller`.
- WebSocket `/ws/signal/<room>?role=user|caller`. The server relays `offer`, `answer`, `ice`, `bye` to the other peer and emits `peer-joined` / `peer-left`. It never sees media.
- The user page is the offerer. On `peer-joined`, or when ICE `failed`, it sends a fresh offer (`iceRestart`). The signalling socket reconnects with backoff.
- `GET /rtc/config` → `iceServers` (STUN by default; TURN via env) and the public join base URL. `GET /qr?data=` → an SVG QR code for the join link.

## 3. Caller transcription (`gnani/prisma_stream.py`, `live.py`)
- The browser resamples to 16 kHz in an `AudioContext({sampleRate:16000})` and an AudioWorklet emits Int16 frames. The backend re-frames them into exactly **1024-byte** frames (512 samples) as the docs require; the cadence is naturally real time.
- Handshake: `x-api-key-id`, `model=prisma-v3.0`, `language_code=indic-auto` (or the user's hint list), `format=codemix`, `x-sample-rate=16000`, `x-idle-timeout-sec=900`, `keyterms`.
- Only finals exist. Each becomes a `TranscriptRecord{speaker:CALLER, text, ts, language, final:true, segment_id}`. Duplicates are dropped by `segment_id`, plus an identical-text-within-5-s guard. Records are ordered by arrival and indexed by `segment_index`.
- If the upstream closes (15-minute cap, idle timeout, network), it reconnects with backoff and the page shows a status. Errors become `stt` status events; the call is never affected.

## 4. Evidence aggregation and risk (`risk/engine.py`)
- The same `Facts` object for the session collects **caller statements, user reports and user answers**, so statement 1 ("account blocked") + 2 ("bank security department") + 3 ("tell me the OTP") combine.
- Each piece of evidence is an `Evidence{indicator, speaker, text, ts, strength}`. Strength is `direct` (the caller said it), `reported` (the user described it) or `answer` (the user said yes to RUKO's question). Each indicator has a `severity` (critical / high / medium / low, from the existing weights) and an explanation.
- Levels, rules and the "never genuine" policy are unchanged. Follow-up questions skip slots the caller transcript already answered.

## 5. Live alerts (`live.py`)
- Only **final** caller transcripts are analysed.
- A spoken alert fires when a sign of severity **medium or higher** becomes present for the first time, or when the level rises to HIGH. Each sign is announced at most once. There is a 10 s cooldown, except a critical sign that hasn't been announced yet may speak after 4 s. When several signs arrive together, only the most severe is spoken.
- The alert text is short and localized (te/hi/hi-en/en), spoken by Timbre, and sent as a `alert` event with `audio_url`. **Silence RUKO** stops voice alerts (no TTS call is made) but risk and transcripts keep updating.

## 6. User interaction (unchanged contract)
- The text box and mic still use `/turn/text` and `/turn/voice64`, on the **same session**. Replies therefore use caller context ("is this real?" → current verdict built from the caller's own statements).
- User turns are logged as `TranscriptRecord{speaker: USER}`.

## 7. Mode B — Android floating companion (deferred, with reasons)
A system overlay needs `SYSTEM_ALERT_WINDOW` (with the `Settings.ACTION_MANAGE_OVERLAY_PERMISSION` flow), a `TYPE_APPLICATION_OVERLAY` window created from native code, and on Android 14+ a foreground service of an allowed type to stay alive. None of this can run inside **Expo Go**: it needs a custom dev build (JDK + Gradle, not installed here) and a native module. Even then, Android doesn't give third-party apps cellular call audio (`CAPTURE_AUDIO_OUTPUT` is system-only). Using an accessibility service for that would be misuse, and it is out of scope. The overlay could only open the existing RUKO assistant for typed or spoken descriptions. Deferred so the primary demo isn't put at risk.

## 8. Running
- HTTP (PC as the RUKO user on `localhost`, the Expo app, automated tests): `uvicorn app.main:app --port 8000`.
- HTTPS (a phone joining over the LAN): `uv run python scripts/make_cert.py` and then `uvicorn ... --port 8443 --ssl-keyfile .cert/key.pem --ssl-certfile .cert/cert.pem`.
- Env: `ICE_STUN_URLS`, `ICE_TURN_URL`, `ICE_TURN_USERNAME`, `ICE_TURN_CREDENTIAL`, `PUBLIC_BASE_URL`.

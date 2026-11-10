# RUKO V2 — Upgrade audit (10 Nov 2026)

## Baseline before any V2 change
- `cd backend; uv run python -m pytest -q` → **90 passed**.
- Mobile: `npx tsc --noEmit` clean; Android bundle exports.
- Live Gnani (earlier today): Prisma REST and Timbre REST verified in 7 language samples, plus scenario conversations end to end (TEST_RESULTS.md).
- **New probe** (`backend/scripts/probe_stream.py`, real API): Prisma realtime `wss://api.vachana.ai/stt/v3/stream` with `model=prisma-v3.0`, `language_code=indic-auto`, `format=codemix`, `x-sample-rate=16000`, 1024-byte PCM frames at 32 ms. It returned two VAD-segmented **final** transcripts ("…bank security department, your account will be blocked today." / "We have sent an OTP to your mobile please tell me the OTP") with `detected_language_code=en-IN`, server latency 128–166 ms. The handshake echo showed `partials_enabled: false`. The docs document **no** partial transcripts (one `transcript` per closed segment, `is_final` always true), so V2 uses finals only.

## Existing components
| Component | Where | Status | V2 decision |
|---|---|---|---|
| Prisma REST adapter | `backend/app/gnani/prisma.py` | working, tested live | **reuse** for user private speech |
| Timbre REST adapter | `backend/app/gnani/timbre.py` | working, tested live | **reuse** for alerts and replies |
| HTTP retry/error mapping | `backend/app/gnani/http.py` | working | reuse; streaming errors mapped onto the same `GnaniError` |
| Indicators (multilingual lexicons, negation, schemes, intents) | `backend/app/risk/indicators.py` | working, 37+ tests | **extend** (bank-impersonation phrases) |
| Risk engine (rules, levels, follow-ups) | `backend/app/risk/engine.py` | working | **extend**: evidence records with speaker, timestamp, strength, severity |
| Conversation manager | `backend/app/conversation/manager.py` | working | **extend**: caller statements feed the same session facts; questions already answered by the caller are skipped automatically, because those slots are filled |
| Localized text (te/hi/hi-en/en) | `backend/app/conversation/*.py` | working | **extend** with caller alerts |
| Sessions, audio cache | `backend/app/sessions.py` | working, in memory | extend Session with a transcript log and alert state |
| FastAPI routes | `backend/app/main.py` | working | add WebSocket signalling, live caller-audio socket, room/QR/config routes, static web app |
| Expo app (simulated call) | `mobile/` | working in Expo Go; voice upload fixed (base64) | **keep unchanged** as the simulated mode |

## Gaps for V2
- No real call. The current call is simulated, with Timbre caller lines.
- No access to a remote audio stream, so caller speech can't be transcribed.
- No transcript model with speaker separation.
- No evidence records (only evidence strings).
- No proactive alerts; RUKO only answers turns.

## Technical constraints found
- **Expo Go cannot run WebRTC** (`react-native-webrtc` needs a native dev build, and this PC has no JDK). V2 Mode A is therefore a **browser app** served by the existing backend. Phones join with Chrome. No install needed.
- **getUserMedia needs a secure context.** `http://localhost` is fine; a phone on the LAN needs **HTTPS**. Added: a self-signed certificate generator and an HTTPS run command (or any HTTPS tunnel).
- Prisma realtime gives finals only, segmented by VAD, with a 15-minute session cap and an idle timeout. The relay reconnects automatically.
- Prisma REST rejects WebM, which is what Chrome's MediaRecorder produces. Private speech is captured as PCM in an AudioWorklet and sent as WAV to the existing `/turn/voice64`.
- Concurrency between one realtime session and REST calls is **not documented**. Tested live (see TEST_RESULTS).
- **Mode B (Android overlay)** needs `SYSTEM_ALERT_WINDOW`, a native module and a foreground service, so it can't run in Expo Go → deferred with an explanation (V2_ARCHITECTURE.md §7).

## New components
`backend/app/signaling.py` (rooms + WebSocket relay), `backend/app/gnani/prisma_stream.py` (realtime STT client), `backend/app/live.py` (caller-audio relay, transcript log, evidence aggregation, alert throttling), `web/` (RUKO user page, caller page, AudioWorklet), `backend/scripts/make_cert.py`, `backend/scripts/live_stream_check.py`, and `e2e/` (two-browser tests with Edge + Playwright and fake microphones).

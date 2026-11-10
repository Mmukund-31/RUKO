# Gnani API integration

Verified against https://docs.gnani.ai on 10 Nov 2026, and by live calls the same day.

## Common
- Base URL: `https://api.vachana.ai`
- Auth header: `X-API-Key-ID: <key>` (backend only; `backend/.env` → `GNANI_API_KEY`)
- Errors: STT envelope `{"success":false,"error":{"type","message"}}`; auth/credit/rate errors `{"detail":{"error_code","message"}}` (401 `INVALID_API_KEY`/`MISSING_API_KEY`, 402, 403 `SCOPE_NOT_ALLOWED`, 429 `RATE_LIMITED`); TTS `{"success":false,"message"}`.
- Retry policy (per docs): connection errors and 429/500/502/503/504, 3 attempts, exponential backoff (0.6 s, 1.2 s). Other 4xx are not retried. Implemented in `backend/app/gnani/http.py`.

## Prisma (speech-to-text) — `backend/app/gnani/prisma.py`
`POST /stt/v3`, `multipart/form-data`:

| Field | RUKO value |
|---|---|
| `audio_file` | the phone's m4a (AAC, 16 kHz mono); format is taken from the file extension |
| `model` | `prisma-v3.0` |
| `language_code` | `indic-auto` (Auto) or a hint list, e.g. `te-IN,en-IN`, `hi-IN,en-IN` |
| `format` | `codemix` (English words stay in Latin script) |
| `keyterms` | OTP, Aadhaar, PAN, KYC, UPI, CVV, PIN, AnyDesk, TeamViewer, CBI, RBI, police |
| `previous_text` | the last few turns (≤600 chars) for context |

Response fields used: `transcript`, `detected_language_code`, `model`, `processing_time`.
Limits: 30 s per request (RUKO stops at 28 s). STT languages: bn, en, gu, hi, kn, ml, mr, pa, ta, te (`-IN`). No Urdu.
Streaming (`wss://api.vachana.ai/stt/v3/stream`) exists but is not used: short utterances over REST were fast enough (~0.55 s end to end).

## Timbre (text-to-speech) — `backend/app/gnani/timbre.py`
`POST /api/v1/tts/inference`, JSON:

```json
{
  "text": "...", "voice": "Lakshmi", "model": "timbre-v3.0", "language": "te-IN", "speed": 0.95,
  "audio_config": {"sample_rate": 24000, "num_channels": 1, "sample_width": 2,
                   "encoding": "linear_pcm", "container": "mp3", "bitrate": "64k"}
}
```
The response is raw `audio/mpeg` bytes. RUKO language → Timbre: te→`te-IN`, hi→`hi-IN`, hi-en→`hi-en`, en→`en-IN`, kn→`kn-IN`, etc.
Voices: Timbre v3.0 voices each speak all 10 languages. RUKO uses *Lakshmi* for replies; the caller voices are *Avinash*, *Yashraj*, *Prakash* and *Devansh*.
SSE and WebSocket streaming exist; not used (replies are short; REST measured 0.8–3.7 s).

## Backend endpoints used by the app
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | key configured? (never returns the key) |
| POST | `/session` · DELETE `/session/{id}` | start / end & clear |
| POST | `/turn/text` | `{session_id, text, language}` |
| POST | `/turn/voice` | multipart `session_id`, `language`, `audio` → Prisma → turn |
| POST | `/speak` | retry Timbre for a reply |
| GET | `/audio/{id}` | generated reply audio (in-memory, 10 min) |
| GET | `/caller/{A-D}` · `/scenarios` | synthetic caller voice (Timbre) and labels |

Turn response: `reply_text, language, audio_url, tts_error, risk{level, score, signs, evidence, missing, main_reason, action, loss_reported, level_text, reason_text, action_text}, followup, done, transcript, detected_language, stt_latency_s, tts_latency_s`.

## Mocks
Mocked Gnani HTTP (`httpx.MockTransport`) is used **only** in `backend/tests/`. The application has no mock or simulated transcription/TTS path: without a key, voice input returns 503 `STT_NOT_CONFIGURED` and replies come back as text with `tts_error: TTS_NOT_CONFIGURED`.

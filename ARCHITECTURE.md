# RUKO — Architecture

```
┌──────────── Phone (Expo Go) ─────────────┐        ┌──────────── PC: FastAPI backend ────────────┐
│ App.tsx  incoming → call → ended         │        │ main.py        HTTP routes, error mapping    │
│ CallScreen    caller audio (GET /caller) │  HTTP  │ gnani/prisma   POST /stt/v3      ──► Gnani   │
│ AssistantSheet  mic / text / caption     │◄──────►│ gnani/timbre   POST /api/v1/tts/inference ─► │
│ AssessmentView  level, reason, action    │        │ conversation/  manager + localized responses │
│ useRuko   expo-audio record + playback   │        │ risk/          indicators + engine (pure)    │
│ api/client  no secrets                   │        │ sessions       in-memory sessions + audio    │
└──────────────────────────────────────────┘        └──────────────────────────────────────────────┘
```

## Components (kept separate)
| Concern | Where | Notes |
|---|---|---|
| Mobile UI | `mobile/src/screens`, `App.tsx` | 3 screens: call, assistant sheet, assessment |
| Audio capture/playback | `mobile/src/audio/useRuko.ts` | m4a 16 kHz mono, 28 s cap, min 0.7 s; one player for RUKO, one for the caller |
| Gnani API service | `backend/app/gnani/` | retries 429/5xx/network ×3 with backoff; maps documented error shapes |
| Conversation manager | `backend/app/conversation/manager.py` | language resolution, yes/no answers to the last question, follow-up choice, finalisation |
| Risk engine | `backend/app/risk/` | pure functions; returns level, score, signs, evidence, missing, action |
| Session state | `backend/app/sessions.py` | in memory, TTL; no DB needed for v1 |

## Turn sequence (voice)
1. App records → `POST /turn/voice` (multipart).
2. Backend → Prisma (`prisma-v3.0`, `indic-auto` or a language hint list, `format=codemix`, `keyterms`, `previous_text`).
3. Transcript → `handle_turn`: indicator hits (clause split, negation in a ±word window) → facts → `assess` → follow-up or final text in the reply language.
4. Backend → Timbre (`timbre-v3.0`, voice Lakshmi, mp3 24 kHz) → audio cached → `audio_url`.
5. App plays it; caption shows the same text. If Timbre fails, the text still arrives with `tts_error` and a "Retry voice" button (no device-TTS fallback).

## Language resolution
Explicit choice wins. In Auto: Prisma's `detected_language_code` (Hindi with mostly Latin text → Hinglish), or script/lexicon detection for typed text. Short answers ("yes", "ledu") keep the session language. Reply templates exist for te / hi / hi-en / en; other languages use English text and the English voice.

## Audio privacy in the demo
Opening RUKO pauses the caller player; recording only uploads to the backend; the simulated caller has no uplink; replies play locally. Speaker toggles `shouldRouteThroughEarpiece`. This demonstrates separate paths inside the app only — it does not prove routing on real cellular calls.

## Why these choices
- **Expo Go + expo-audio**: recording and playback work without a native build, fastest to an Android demo.
- **REST Prisma, not streaming**: utterances are short (<30 s); REST gave ~0.5–0.6 s latency in testing, simpler and reliable over Wi-Fi.
- **REST Timbre**: whole replies are short; 1–3.5 s generation measured.
- **Deterministic engine**: explainable, testable, no extra paid AI provider.

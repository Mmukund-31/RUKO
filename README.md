# RUKO — Pause. Verify. Stay safe.

RUKO is a voice-first, multilingual scam-safety companion. During a suspicious phone call you tap the floating RUKO button, explain what the caller wants (by voice or text, in your own language), and RUKO asks one or two short follow-up questions and speaks practical guidance and a final risk assessment.

Built for the **Gnani AI Great Indian AI Internship Challenge**.

| Gnani technology | Used for |
|---|---|
| **Gnani Prisma v3.0** (speech-to-text, `POST /stt/v3`, `indic-auto` + `codemix`) | Transcribing what the user tells RUKO |
| **Gnani Timbre v3.0** (text-to-speech, `POST /api/v1/tts/inference`, voice *Lakshmi*) | Every RUKO spoken reply, and the synthetic caller voices in the simulated call |

Evon is **not** used (it is not available on the API platform). No other AI provider is used: the risk engine is deterministic and explainable.

> **Demo scope.** The phone call is simulated inside the app with synthetic callers. RUKO does not capture real cellular call audio or overlay the system dialer — that is a separate capability with OS restrictions.

---

## How it works

```
Simulated call ──tap RUKO──► Assistant sheet (caller audio paused)
                                 │ mic (m4a, 16 kHz mono)      │ text
                                 ▼                             ▼
                         RUKO backend (FastAPI) ── holds the Gnani key
                                 │
          Gnani Prisma ◄─────────┤  transcript + detected language
                                 ▼
               Conversation manager → Risk engine (rules, multilingual lexicons)
                                 │  reply text (te / hi / Hinglish / en)
          Gnani Timbre ◄─────────┤
                                 ▼
                    MP3 played on the phone + short caption
```

Outcomes: **HIGH RISK**, **SUSPICIOUS**, or **INSUFFICIENT INFORMATION**. RUKO never says a caller is genuine. For active fraud it points to the **1930** helpline and **https://cybercrime.gov.in/**.

See [ARCHITECTURE.md](ARCHITECTURE.md), [API_INTEGRATION.md](API_INTEGRATION.md), [PRODUCT_SPEC.md](PRODUCT_SPEC.md), [TEST_RESULTS.md](TEST_RESULTS.md).

## Folder structure

```
RUKO/
  backend/                     FastAPI service (the only place the Gnani key lives)
    app/main.py                routes: /session /turn/text /turn/voice /speak /audio /caller /scenarios /health
    app/config.py              settings from backend/.env
    app/gnani/                 prisma.py, timbre.py, http.py (retries + error mapping)
    app/risk/                  indicators.py (multilingual lexicons, negation), engine.py (rules)
    app/conversation/          manager.py (turns, follow-ups, language), responses.py (te/hi/hi-en/en text)
    app/scenarios.py           synthetic demo callers A–D
    app/sessions.py            in-memory sessions + audio cache (TTL, nothing on disk)
    tests/                     pytest (engine, conversation, adapters, API)
    scripts/live_check.py      real Timbre→Prisma round-trip per language
    scripts/e2e_check.py       real end-to-end run of scenarios against a running backend
    .env.example
  mobile/                      Expo (React Native, TypeScript), runs in Expo Go
    App.tsx                    incoming call → active call → ended (scenario picker)
    src/screens/               CallScreen, AssistantSheet, AssessmentView
    src/audio/useRuko.ts       recording, playback, conversation state, error handling
    src/api/client.ts          backend client
    src/i18n/strings.ts        UI labels (te, hi, Hinglish, en)
    .env.example
```

## Setup

Prerequisites: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+, an Android phone with **Expo Go** (Play Store), PC and phone on the same Wi-Fi.

### 1. Gnani credentials
1. Create a key at https://app.gnani.ai/voice/api-keys
2. `copy backend\.env.example backend\.env` and set `GNANI_API_KEY=...`

`.env` is git-ignored. The key is only sent from the backend to `api.vachana.ai` in the `X-API-Key-ID` header; it is never logged, returned, or bundled into the app.

| Variable | Default | Meaning |
|---|---|---|
| `GNANI_API_KEY` | — (required) | Gnani API key |
| `GNANI_BASE_URL` | `https://api.vachana.ai` | API base |
| `PRISMA_MODEL` | `prisma-v3.0` | STT model |
| `PRISMA_FORMAT` | `codemix` | keeps English words in Latin script |
| `TIMBRE_MODEL` | `timbre-v3.0` | TTS model |
| `TIMBRE_VOICE` | `Lakshmi` | v3.0 voice (speaks all 10 languages) |
| `TIMBRE_SPEED` | `0.95` | slightly slower for elderly listeners |
| `HTTP_TIMEOUT_S` | `30` | per-request timeout |

### 2. Backend
```powershell
cd backend
uv sync
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Check: open `http://localhost:8000/health` → `"gnani_key_configured": true`.
Windows may ask to allow Python through the firewall — allow it on **Private** networks so the phone can connect.

### 3. Mobile app
```powershell
cd mobile
npm install
# point the app at your PC (find the IP with `ipconfig`, Wi-Fi adapter):
echo EXPO_PUBLIC_API_URL=http://<YOUR-PC-IP>:8000 > .env
npx expo start
```
Scan the QR code with Expo Go. If Wi-Fi blocks it, use USB: `adb reverse tcp:8000 tcp:8000` (adb is in `%LOCALAPPDATA%\Android\Sdk\platform-tools`), set `EXPO_PUBLIC_API_URL=http://localhost:8000`, and run `npx expo start --tunnel` or `--localhost`.

## Testing

```powershell
cd backend
uv run python -m pytest -q                 # 106 unit/API tests (Gnani HTTP is mocked in tests only)
uv run python scripts/live_check.py        # REAL Timbre + Prisma, 7 language samples
uv run python scripts/e2e_check.py         # REAL end-to-end scenarios (backend must be running)
cd ..\mobile; npx tsc --noEmit             # type-check the app
```

**Test Prisma alone:** `uv run python scripts/live_check.py te hi-en` prints the transcript, detected language and latency. Or with curl:
`curl -X POST http://localhost:8000/turn/voice -F session_id=<id from POST /session> -F audio=@clip.m4a`

**Test Timbre alone:** `curl -X POST http://localhost:8000/speak -H "Content-Type: application/json" -d "{\"text\":\"నమస్కారం\",\"language\":\"te\"}"` → then GET the returned `audio_url`.

## Demo scenarios (synthetic)

On the start screen pick A–D (or long-press the caller name during a call to switch). Accept the call, listen to the caller, tap the green RUKO shield, then speak or type.

| | Caller (Timbre voice) | Say / type to RUKO | Expected |
|---|---|---|---|
| **A** Card block + OTP | "SBI Card Services", Hinglish, 5 escalating lines | "Credit card block call" → *haan* | Card-block pattern recognised, asks for card/CVV/OTP, *yes* → HIGH RISK, call the number on your card, 1930 |
| **B** Digital arrest | "Crime branch inspector", Hindi | "पुलिस वाला कह रहा है मैं डिजिटल अरेस्ट में हूँ, तुरंत पैसे भेजो" | HIGH RISK: authority + threat + money, do not transfer, verify officially |
| **C** KYC update | Mobile network, English | "They say my KYC needs updating" → *no / no / no* | Asks OTP/PIN → app/screen share → money; ends INSUFFICIENT INFO with KYC-specific advice. "They want my Aadhaar and date of birth" → SUSPICIOUS; plus "SIM blocked today" → HIGH |
| **D** Unclear | Service centre, Telugu | "సర్వీస్ సెంటర్ నుండి కనెక్షన్ సమస్య గురించి కాల్ వచ్చింది" | INSUFFICIENT INFO + follow-up question |


## V2 — Live call mode (real WebRTC call, primary demo)

This is a real two-device call in the browser:
- RUKO hears the **caller's** audio stream on a separate path and transcribes it with **Gnani Prisma realtime** (`wss://api.vachana.ai/stt/v3/stream`).
- It combines evidence across statements and speaks short **Gnani Timbre** warnings.
- The user can ask RUKO privately at any time; the caller can't hear.

Design: [V2_ARCHITECTURE.md](V2_ARCHITECTURE.md). Audit: [V2_UPGRADE_AUDIT.md](V2_UPGRADE_AUDIT.md).

### Run
```powershell
cd backend
uv sync
uv run python scripts/make_cert.py          # once: self-signed HTTPS cert for this PC's LAN IP
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile .cert/key.pem --ssl-certfile .cert/cert.pem
```
Phones need **HTTPS** to use the microphone, which is why there is a server on port 8443. The plain HTTP server on 8000 still serves the Expo app and `localhost` testing.

### Connect the second phone (the caller)
1. On the PC (the RUKO user, **wearing headphones**), open `https://localhost:8443` in Chrome or Edge. Accept the certificate warning once, then tap **Start call**.
2. A QR code and a link such as `https://192.168.1.7:8443/join/AB12CD` appear. On the caller phone, on the same Wi-Fi, scan it with Chrome. Tap *Advanced → Proceed* on the certificate warning, then **Join call**, and allow the mic.
3. The call connects. The caller page shows a demo script to read aloud in English, Hinglish or Telugu.

On other networks, set `ICE_TURN_URL`, `ICE_TURN_USERNAME` and `ICE_TURN_CREDENTIAL`, because STUN alone doesn't get through every NAT. Set `PUBLIC_BASE_URL` if the join link should use another host, such as an HTTPS tunnel.

### What the user sees
- **Status:** connection, call mic, caller audio, and whether RUKO is listening.
- **Live transcript:** the **Caller** on the left, **You (private)** on the right, RUKO alerts in the centre.
- **Risk badge:** a small badge showing the risk level and its main reason.
- **Ask RUKO:** opens the existing assistant, with a mic and a text box.
  - Opening it **mutes your call mic**. The caller hears silence, and the call stays connected.
  - The caller keeps talking, at lower volume.
  - Your question goes through a *second* microphone track that is never added to the call.
  - Only **Back to call** turns your call mic back on.
- **Alerts:** outside private mode, RUKO pauses your call mic while it speaks an alert and turns it back on afterwards.
- **Spoken alerts toggle:** silences RUKO's voice; detection and the risk badge keep updating.

### Test private-audio isolation
**Automated.** This uses real WebRTC and real Gnani between two separate browser processes, each with a fake microphone:
```powershell
cd e2e; npm install; node live_call.e2e.mjs http://localhost:8000 chrome
```
or, over HTTPS, `node live_call.e2e.mjs https://<LAN-IP>:8443 msedge`.

The test measures how much audio energy reaches the caller from the user in each state. It must be:
- above 0 in a normal call,
- exactly 0 in private mode, while recording a private question, and while RUKO speaks.

It also checks that the call track is the only track ever in `RTCPeerConnection.getSenders()`. The fake microphones play synthetic Timbre speech made by `backend/scripts/make_fake_mics.py`.

**Manual:**
1. During the call, open **Ask RUKO** and talk. The caller phone must hear nothing.
2. Let RUKO answer. The caller must still hear nothing.
3. Tap **Back to call**. The caller hears you again.

**Use headphones.** A browser can't stop the caller hearing your loudspeaker through your microphone. The page warns when it detects no headphone-like output device.

### Test caller transcription and the scam scenarios
To check Prisma realtime on its own, run `uv run python scripts/probe_stream.py`. It streams a Timbre-spoken scam sentence to Prisma realtime and prints the messages that come back.

For a live test, have the caller say:

| Scenario | Caller says | Expected |
|---|---|---|
| OTP scam | "bank security department… blocked today… tell me the OTP" | authority + threat + urgency → OTP warning (spoken) → **HIGH** |
| Digital arrest | "मैं क्राइम ब्रांच से इंस्पेक्टर… डिजिटल अरेस्ट… तुरंत पैसे ट्रांसफर" | police pattern + money → **HIGH**, money warning |
| Fake KYC | "Your KYC is pending" → "tell me your Aadhaar number and date of birth" | INSUFFICIENT → **SUSPICIOUS** (ID request), ID warning |
| Investment | "invest today, guaranteed returns, double your money" | lure + money → **HIGH** |
| Innocent bank enquiry | "HDFC about your loan… visit the branch… we will never ask your OTP" | stays **INSUFFICIENT**, no alert |

Then ask RUKO privately, for example "ఇది నిజమేనా? నేను ఏం చేయాలి?" or "kya karu?". The answer uses what the caller said.

### Mode B — Android floating overlay
This is not implemented, on purpose:
- It needs `SYSTEM_ALERT_WINDOW`, a native `TYPE_APPLICATION_OVERLAY` module and a foreground service, none of which run in Expo Go.
- Android also doesn't give third-party apps cellular call audio, so an overlay could only open the assistant.

Details are in V2_ARCHITECTURE.md §7.


## Context awareness

RUKO recognises the scam *pattern* — police/digital arrest, card or account block, KYC, prize/lottery, investment, refund, job offer, courier, electricity/SIM — and uses it to:
- acknowledge what it understood ("Calls saying your card will be blocked are a very common scam."),
- choose and word the follow-up questions (card → "card number, CVV or OTP?"; police → "pay a fine or move money to a 'safe' account?"; prize → "a fee or tax to receive it?"),
- give pattern-specific verification advice (card → number on the back of your card; police → 112 / local station; KYC → branch or official app).

It also tells *mentioning* an ID apart from being *asked for* one, answers "is this real?" / "what should I do?" (also in Telugu/Hindi) with the current verdict, handles "yes, they want a fee" as a statement rather than a bare yes, and keeps the whole conversation on screen. A pattern alone is never a verdict.

## Language support (tested status)

| Language | Speech in (Prisma) | RUKO replies (text) | RUKO voice (Timbre) |
|---|---|---|---|
| Telugu | ✅ tested (live, synthetic speech) | ✅ hand-written | ✅ tested |
| Hindi | ✅ tested | ✅ hand-written | ✅ tested |
| English (Indian) | ✅ tested | ✅ hand-written | ✅ tested |
| Hinglish | ✅ tested (transcribed as Devanagari + English words; reply in Hindi) | ✅ typed Hinglish → Latin-script Hinglish reply | ✅ tested (`hi-en`) |
| Telugu-English mix | ✅ tested (romanised Telugu speech → Telugu script + English words) | ✅ Telugu | ✅ tested |
| Kannada | ✅ tested | ⚠️ falls back to English text | English voice |
| Tamil | ✅ tested | ⚠️ falls back to English text | English voice |
| Malayalam, Marathi, Bengali, Gujarati, Punjabi | supported by Prisma per docs, **not tested** | English fallback | English voice |
| Urdu | ❌ not supported by Prisma | — | — |

"Tested" means real Gnani API calls on Timbre-generated speech (see TEST_RESULTS.md). Real human speech, especially elderly and noisy-phone speech, should be tested on the device before claiming quality.

## Privacy

- No raw audio is stored: the phone deletes each recording right after reading it, the backend forwards it to Prisma and discards it; sessions and reply audio live in memory only (30 min / 10 min TTL).
- "End & clear" deletes the session on the server. Ending the call does the same.
- RUKO never asks for Aadhaar, PAN, OTP, PIN or account numbers, never contacts anyone automatically, and is not an official government, bank or police service.
- RUKO's microphone audio only goes to the RUKO backend; the simulated caller has no uplink. While RUKO is open the caller keeps talking at low volume, and is put on hold only while you record, so it can't leak into your recording.

## Known limitations

- Simulated call only; no real cellular call capture or dialer overlay.
- The risk engine is rule-based with lexicons for English, Hindi (Devanagari + romanised) and Telugu (script + romanised). Phrasings outside the lexicon may be missed → it then asks follow-up questions rather than guessing. Other languages rely on English/code-mixed keywords (OTP, bank, police…), which Prisma `codemix` keeps in Latin script.
- Replies for Kannada, Tamil and others are in English.
- Spoken Hinglish is transcribed in Devanagari, so RUKO answers in Hindi (Devanagari) rather than romanised Hinglish.
- Final assessments are ~15–25 s of speech; the user can tap to stop and read the caption.
- Prisma REST limit is 30 s per recording; RUKO auto-stops at 28 s.
- In-memory sessions: restarting the backend clears conversations.
- No authentication on the local backend — run it on a trusted network only.

## Recording the challenge demo video (≈60 s)

1. Start backend and `npx expo start`; open the app on the phone; Speaker on; screen-record the phone (Android quick-settings → Screen record, with *device audio + mic*).
2. Pick **Scenario A** → Accept → let the caller line play once.
3. Tap the RUKO shield → tap mic → say in Telugu or Hinglish what the caller wants (e.g. *"Bank nunchi call chesi account block avutundi antunnaru"*).
4. Show the transcript (Prisma) and RUKO's spoken follow-up (Timbre): *"…OTP చెప్పమని అడిగారా?"*
5. Answer "అవును" → RUKO speaks HIGH RISK + guidance; show the assessment screen with 1930 / cybercrime.gov.in.
6. Tap **Back to call** → caller resumes → End call.
7. Post on LinkedIn/X: what RUKO does, that it uses **Gnani Prisma (STT)** and **Gnani Timbre (TTS)**, tag **Gnani AI**, and add `#GnaniAI #GreatIndianAIInternshipChallenge`. Use only synthetic data. No purchased engagement.

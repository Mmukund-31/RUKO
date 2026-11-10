"""Live Gnani check: REAL Timbre + Prisma calls (needs GNANI_API_KEY in backend/.env).

For each language: Timbre speaks a scam-description sentence -> saved as MP3 ->
sent back to Prisma -> transcript, detected language, latency and the risk
engine's verdict are printed. A round-trip on synthetic speech is a useful
smoke test, but it is not a substitute for testing real human speech on the
phone (see README).

Usage:  uv run python scripts/live_check.py [te hi en hi-en kn ...]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.gnani import GnaniError, PrismaClient, TimbreClient  # noqa: E402
from app.risk import assess, find_hits, Facts  # noqa: E402

OUT = Path(__file__).parent / "out"

SAMPLES = {
    "te": "బ్యాంక్ నుండి కాల్ చేస్తున్నామని చెప్పి, నా OTP చెప్పమని అడుగుతున్నారు.",
    "hi": "कॉलर कह रहा है कि वह पुलिस से है और मुझे तुरंत पैसे भेजने होंगे।",
    "en": "The caller says my KYC must be updated today and is asking me to install an app.",
    "hi-en": "Bank wale bol rahe hain ki account block ho jayega, OTP batao.",
    "kn": "ಬ್ಯಾಂಕ್‌ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇವೆ ಎಂದು ಹೇಳಿ OTP ಕೇಳುತ್ತಿದ್ದಾರೆ.",
    "ta": "வங்கியிலிருந்து அழைப்பதாகச் சொல்லி OTP கேட்கிறார்கள்.",
    "te-en": "Bank nunchi call chesi naa OTP cheppamani adugutunnaru, account block avutundi antunnaru.",
}
# Timbre language used to *speak* each sample, and Prisma hint used to transcribe it.
TTS_AS = {"te-en": "te"}
STT_AS = {"te-en": "te"}


async def main(langs: list[str]) -> int:
    st = get_settings()
    if not st.key_configured:
        print("GNANI_API_KEY is not set in backend/.env - cannot run live check.")
        return 2
    key = st.gnani_api_key.get_secret_value()  # type: ignore[union-attr]
    OUT.mkdir(exist_ok=True)
    results = []
    async with httpx.AsyncClient(timeout=st.http_timeout_s) as http:
        tts = TimbreClient(http, st.gnani_base_url, key, st.timbre_model, st.timbre_voice, st.timbre_speed)
        stt = PrismaClient(http, st.gnani_base_url, key, st.prisma_model, st.prisma_format)
        for lang in langs:
            text = SAMPLES[lang]
            row: dict = {"lang": lang, "input": text}
            try:
                sp = await tts.synthesize(text, TTS_AS.get(lang, lang))
                path = OUT / f"tts_{lang}.mp3"
                path.write_bytes(sp.audio)
                row |= {"tts_ok": True, "tts_latency_s": sp.latency_s, "tts_bytes": len(sp.audio)}
                for hint in ("auto", STT_AS.get(lang, lang)):
                    t0 = time.perf_counter()
                    tr = await stt.transcribe(sp.audio, "speech.mp3", hint)
                    f = Facts()
                    f.apply_hits(find_hits(tr.text))
                    r = assess(f)
                    row[f"stt_{hint}"] = {
                        "transcript": tr.text,
                        "detected": tr.detected_language,
                        "latency_s": round(time.perf_counter() - t0, 3),
                        "processing_time": tr.processing_time,
                        "risk": r.level.value,
                        "signs": r.signs,
                    }
                    await asyncio.sleep(0.3)  # some accounts allow one request at a time
            except GnaniError as e:
                row["error"] = str(e)
            results.append(row)
            print(json.dumps(row, ensure_ascii=False, indent=2))
    (OUT / "live_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {OUT / 'live_results.json'}")
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    args = sys.argv[1:] or list(SAMPLES)
    raise SystemExit(asyncio.run(main(args)))

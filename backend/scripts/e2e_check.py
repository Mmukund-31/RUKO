"""End-to-end check against a RUNNING backend (real Gnani calls).

1. Plays demo scenarios A-D as text conversations through /turn/text.
2. Downloads each spoken reply (Timbre) and sends it back through /turn/voice
   on a fresh session (Prisma), so the spoken audio is verified by transcription.
3. Fetches synthetic caller audio for each scenario.

Usage: uv run python scripts/e2e_check.py [http://localhost:8000]
"""

from __future__ import annotations

import base64
import json
import sys
import time

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")

CONVERSATIONS = {
    "A_otp_hinglish": ("auto", ["SBI se call hai, woh OTP maang rahe hain"]),
    "B_digital_arrest_hindi": ("auto", ["पुलिस वाला कह रहा है कि मैं डिजिटल अरेस्ट में हूँ और तुरंत पैसे भेजो"]),
    "C_kyc_english_all_no": ("auto", ["They say my KYC needs to be updated", "no", "no", "no"]),
    "C_kyc_telugu_fee": ("auto", ["నా KYC అప్డేట్ చేయాలని కాల్ వచ్చింది", "లేదు", "అవును, వెంటనే ఫీజు కట్టమంటున్నారు"]),
    "card_block_te_user_case": ("te", ["Credit card block call", "no", "is this real?"]),
    "id_request_en": ("auto", ["The caller is asking for my Aadhaar number and date of birth", "no", "they say SIM will be blocked today"]),
    "D_unclear_telugu": ("auto", ["సర్వీస్ సెంటర్ నుండి కనెక్షన్ సమస్య గురించి కాల్ వచ్చింది"]),
}


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=60)
    print("health:", c.get("/health").json())
    ok = True
    report = {}
    for name, (lang, turns) in CONVERSATIONS.items():
        sid = c.post("/session").json()["session_id"]
        rows = []
        for text in turns:
            t0 = time.perf_counter()
            r = c.post("/turn/text", json={"session_id": sid, "text": text, "language": lang})
            j = r.json()
            row = {
                "user": text,
                "reply": j.get("reply_text"),
                "lang": j.get("language"),
                "level": j["risk"]["level"],
                "followup": j.get("followup"),
                "done": j.get("done"),
                "tts": bool(j.get("audio_url")),
                "tts_error": j.get("tts_error"),
                "tts_latency_s": j.get("tts_latency_s"),
                "turn_latency_s": round(time.perf_counter() - t0, 3),
            }
            if j.get("audio_url"):
                audio = c.get(j["audio_url"]).content
                row["audio_bytes"] = len(audio)
                # Verify the spoken reply by transcribing it with Prisma (fresh session).
                vsid = c.post("/session").json()["session_id"]
                v = c.post("/turn/voice64", json={"session_id": vsid, "language": "auto", "ext": "mp3",
                                                  "audio_b64": base64.b64encode(audio).decode()}).json()
                row["reply_heard_by_prisma"] = v.get("transcript")
                row["reply_detected_lang"] = v.get("detected_language")
                c.delete(f"/session/{vsid}")
            else:
                ok = False
            rows.append(row)
            time.sleep(0.3)
        c.delete(f"/session/{sid}")
        report[name] = rows
        print(f"\n=== {name}")
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    scen = c.get("/scenarios").json()
    for sc, info in scen.items():
        for i in range(len(info["lines"])):
            t0 = time.perf_counter()
            r = c.get(f"/caller/{sc}/{i}")
            print(f"caller {sc}/{i}: {r.status_code} {len(r.content)} bytes {time.perf_counter()-t0:.2f}s")
            ok &= r.status_code == 200
    with open("scripts/out/e2e_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

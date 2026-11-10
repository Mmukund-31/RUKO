"""Generate SYNTHETIC speech WAVs (real Timbre) used as fake microphones in the two-browser E2E test.

e2e/fixtures/caller.wav : the scam caller's script (English, male voice), with pauses
e2e/fixtures/user.wav   : the RUKO user's private question (Telugu, female voice)
"""

from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

OUT = Path(__file__).resolve().parent.parent.parent / "e2e" / "fixtures"
SR = 16000

CALLER = [
    "Hello sir, I am calling from your bank security department. Your account has a verification problem.",
    "Your account will be blocked today if you do not complete verification.",
    "We have sent an OTP to your mobile. Please tell me the OTP.",
]
USER = ["కాలర్ OTP అడుగుతున్నారు. ఇది నిజమేనా? నేను ఏం చేయాలి?"]


def wav(pcm: bytes) -> bytes:
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


async def tts(c: httpx.AsyncClient, key: str, base: str, text: str, voice: str, lang: str) -> bytes:
    r = await c.post(f"{base}/api/v1/tts/inference", headers={"X-API-Key-ID": key}, json={
        "text": text, "voice": voice, "model": "timbre-v3.0", "language": lang,
        "audio_config": {"sample_rate": SR, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "raw"}})
    r.raise_for_status()
    return r.content


async def main() -> None:
    st = get_settings()
    key = st.gnani_api_key.get_secret_value()
    OUT.mkdir(parents=True, exist_ok=True)
    gap = b"\x00\x00" * int(SR * 1.2)
    async with httpx.AsyncClient(timeout=60) as c:
        caller = b"".join([await tts(c, key, st.gnani_base_url, t, "Avinash", "en-IN") + gap for t in CALLER])
        user = await tts(c, key, st.gnani_base_url, USER[0], "Lakshmi", "te-IN") + gap * 2
    (OUT / "caller.wav").write_bytes(wav(caller))
    (OUT / "user.wav").write_bytes(wav(user))
    print(f"caller.wav {len(caller)/SR/2:.1f}s, user.wav {len(user)/SR/2:.1f}s -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())

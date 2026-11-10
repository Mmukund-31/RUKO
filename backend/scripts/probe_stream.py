"""Probe Gnani Prisma realtime STT (wss://api.vachana.ai/stt/v3/stream) with REAL calls.

Timbre speaks a sentence as 16 kHz PCM WAV; the PCM is streamed in 1024-byte frames
(512 samples, 32 ms) at real-time cadence, as the docs require. Prints every server message.
Usage: uv run python scripts/probe_stream.py [language_code]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

TEXT = ("Hello sir, I am calling from your bank security department. Your account will be blocked today. "
        "We have sent an OTP to your mobile. Please tell me the OTP.")


async def main(lang: str) -> None:
    st = get_settings()
    key = st.gnani_api_key.get_secret_value()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{st.gnani_base_url}/api/v1/tts/inference", headers={"X-API-Key-ID": key}, json={
            "text": TEXT, "voice": "Avinash", "model": "timbre-v3.0", "language": "en-IN",
            "audio_config": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                             "encoding": "linear_pcm", "container": "raw"}})
        r.raise_for_status()
        pcm = r.content
    out = Path(__file__).parent / "out"; out.mkdir(exist_ok=True)
    print(f"TTS raw PCM: {len(pcm)} bytes = {len(pcm)/32000:.1f}s")
    url = st.gnani_base_url.replace("https://", "wss://") + "/stt/v3/stream"
    headers = {"x-api-key-id": key, "language_code": lang, "model": st.prisma_model,
               "x-sample-rate": "16000", "format": "codemix"}
    t0 = time.perf_counter()
    async with websockets.connect(url, additional_headers=headers, max_size=2**22) as ws:
        async def reader():
            async for msg in ws:
                print(f"[{time.perf_counter()-t0:5.2f}s]", msg if isinstance(msg, str) else f"<{len(msg)} bytes>")
        task = asyncio.create_task(reader())
        silence = b"\x00\x00" * 512
        for i in range(0, len(pcm), 1024):
            frame = pcm[i:i + 1024].ljust(1024, b"\x00")
            await ws.send(frame)
            await asyncio.sleep(0.032)
        for _ in range(60):  # ~2 s trailing silence so VAD closes the utterance
            await ws.send(silence)
            await asyncio.sleep(0.032)
        await asyncio.sleep(3)
        await ws.close()
        await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "indic-auto"))

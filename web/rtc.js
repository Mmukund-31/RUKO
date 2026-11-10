// Shared WebRTC + signalling helpers (used by the RUKO user page and the caller page).

export const wsBase = () => (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host;

export async function rtcConfig() {
  try {
    const r = await fetch('/rtc/config');
    const j = await r.json();
    return { iceServers: j.iceServers };
  } catch {
    return { iceServers: [{ urls: ['stun:stun.l.google.com:19302'] }] };
  }
}

/** Signalling socket with automatic reconnect. `onMessage(msg)`; `onState(state)`. */
export class Signal {
  constructor(room, role, { onMessage, onState }) {
    this.room = room; this.role = role; this.onMessage = onMessage; this.onState = onState || (() => {});
    this.closed = false; this.attempt = 0; this.queue = [];
    this.open();
  }
  open() {
    this.onState(this.attempt ? 'reconnecting' : 'connecting');
    const ws = (this.ws = new WebSocket(`${wsBase()}/ws/signal/${this.room}?role=${this.role}`));
    ws.onopen = () => { this.attempt = 0; this.onState('open'); this.queue.splice(0).forEach((m) => ws.send(m)); };
    ws.onmessage = (e) => { try { this.onMessage(JSON.parse(e.data)); } catch {} };
    ws.onclose = (e) => {
      if (this.closed) return;
      if (e.code === 4404) { this.onState('no-room'); return; }
      if (e.code === 4409) { this.onState('replaced'); return; }
      this.attempt += 1;
      this.onState('reconnecting');
      setTimeout(() => this.open(), Math.min(1000 * 2 ** this.attempt, 8000));
    };
  }
  send(msg) {
    const s = JSON.stringify(msg);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(s); else this.queue.push(s);
  }
  close() { this.closed = true; try { this.ws.close(); } catch {} }
}

/** Microphone for the CALL (sent to the peer). Echo cancellation on. */
export async function getCallMic() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    video: false,
  });
  return stream.getAudioTracks()[0];
}

export function micErrorText(e) {
  if (!window.isSecureContext) return 'The microphone needs a secure page. Open this page with https:// (see README).';
  if (e && (e.name === 'NotAllowedError' || e.name === 'SecurityError')) return 'Microphone permission was denied. Allow it in the browser and try again.';
  if (e && e.name === 'NotFoundError') return 'No microphone found.';
  return 'Could not start the microphone.';
}

export function fmtTime(s) {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** Float32 [-1,1] -> Int16 little-endian. */
export function floatToInt16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const v = Math.max(-1, Math.min(1, f32[i]));
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return out;
}

/** 16 kHz mono Int16 chunks -> WAV Blob (Prisma REST accepts WAV; not WebM). */
export function encodeWav(chunks, sampleRate = 16000) {
  const n = chunks.reduce((a, c) => a + c.length, 0);
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const w = (o, s) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)));
  w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true);
  let o = 44;
  for (const c of chunks) for (let i = 0; i < c.length; i++, o += 2) v.setInt16(o, c[i], true);
  return new Blob([buf], { type: 'audio/wav' });
}

export async function blobToBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

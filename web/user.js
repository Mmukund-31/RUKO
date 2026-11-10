// RUKO user side of the live call.
//
// Audio paths (kept separate on purpose):
//   callTrack   = getUserMedia #1 -> RTCPeerConnection sender (the ONLY track ever sent to the caller)
//   remote      = caller's WebRTC track -> <audio id=callerAudio> (hear) + AudioWorklet -> /ws/live -> Prisma realtime
//   privateTrack= getUserMedia #2 (only while asking RUKO) -> AudioWorklet -> WAV -> /turn/voice64 -> Prisma REST
//   RUKO voice  = Timbre mp3 -> <audio id=rukoAudio> (local playback only; not a MediaStream track)
import { Signal, rtcConfig, getCallMic, micErrorText, fmtTime, floatToInt16, encodeWav, blobToBase64, wsBase } from './rtc.js';

const $ = (id) => document.getElementById(id);
const show = (id, on = true) => $(id).classList.toggle('hidden', !on);

const LANGS = [['auto', 'Auto'], ['te', 'తెలుగు'], ['hi', 'हिन्दी'], ['en', 'English'], ['hi-en', 'Hinglish'],
  ['kn', 'ಕನ್ನಡ'], ['ta', 'தமிழ்'], ['ml', 'മലയാളം'], ['mr', 'मराठी'], ['bn', 'বাংলা'], ['gu', 'ગુજરાતી'], ['pa', 'ਪੰਜਾਬੀ']];
const UI = {
  en: { tap: 'Tap and ask RUKO', listening: 'Listening… tap to stop', transcribing: 'Understanding…', thinking: 'Thinking…', speaking: 'Speaking… tap to stop', type: 'Or type your question' },
  te: { tap: 'నొక్కి RUKO ని అడగండి', listening: 'వింటున్నాను… ఆపడానికి నొక్కండి', transcribing: 'అర్థం చేసుకుంటున్నాను…', thinking: 'ఆలోచిస్తున్నాను…', speaking: 'మాట్లాడుతున్నాను… ఆపడానికి నొక్కండి', type: 'లేదా మీ ప్రశ్న టైప్ చేయండి' },
  hi: { tap: 'दबाइए और RUKO से पूछिए', listening: 'सुन रही हूँ… रोकने के लिए दबाइए', transcribing: 'समझ रही हूँ…', thinking: 'सोच रही हूँ…', speaking: 'बोल रही हूँ… रोकने के लिए दबाइए', type: 'या अपना सवाल टाइप कीजिए' },
};
const LEVEL_LABEL = { HIGH_RISK: 'HIGH RISK', SUSPICIOUS: 'SUSPICIOUS', INSUFFICIENT_INFORMATION: 'NOT ENOUGH INFORMATION' };

const S = {
  sid: null, room: null, cfg: null, pc: null, sig: null, live: null, ctx: null,
  callTrack: null, privateTrack: null, privateStop: null,
  userMuted: false, privateMode: false, autoPaused: false, rukoPlaying: false,
  choice: 'auto', lang: 'en', voice: true, status: 'idle', risk: null,
  started: 0, timer: null, callerPcm: [], callerPcmLen: 0, sentCallerFrames: 0,
};

// ---------------------------------------------------------------- start / signalling
$('startBtn').onclick = start;
$('againBtn').onclick = () => location.reload();

async function start() {
  show('startErr', false);
  try {
    S.ctx = new AudioContext({ sampleRate: 16000 });
    await S.ctx.audioWorklet.addModule('/web/pcm-worklet.js');
    S.callTrack = await getCallMic();
  } catch (e) {
    $('startErr').textContent = e && e.name ? micErrorText(e) : 'Your browser could not start audio. Use Chrome.';
    show('startErr');
    return;
  }
  S.cfg = await rtcConfig();
  S.sid = (await (await fetch('/session', { method: 'POST' })).json()).session_id;
  const room = await (await fetch('/rtc/room', { method: 'POST' })).json();
  S.room = room.room;
  $('roomId').textContent = $('roomId2').textContent = room.room;
  $('joinUrl').textContent = room.join_url;
  $('qr').src = '/qr?data=' + encodeURIComponent(room.join_url);
  show('insecure', !room.secure);
  show('start', false); show('waiting');
  S.sig = new Signal(S.room, 'user', { onMessage: onSignal, onState: (s) => s === 'reconnecting' && setChip('connChip', 'amber', 'signalling reconnecting') });
  checkHeadphones();
}

function newPc() {
  if (S.pc) S.pc.close();
  const pc = (S.pc = new RTCPeerConnection(S.cfg));
  pc.addTrack(S.callTrack, new MediaStream([S.callTrack])); // the ONLY outgoing track
  pc.onicecandidate = (e) => e.candidate && S.sig.send({ type: 'ice', candidate: e.candidate });
  pc.ontrack = (e) => attachCaller(e.streams[0] || new MediaStream([e.track]));
  pc.onconnectionstatechange = () => {
    const st = pc.connectionState;
    setChip('connChip', st === 'connected' ? 'ok' : st === 'failed' || st === 'disconnected' ? 'bad' : 'amber', st);
    if (st === 'connected') enterCall();
    if (st === 'failed') makeOffer(true); // ICE restart
  };
  return pc;
}

async function makeOffer(restart) {
  if (!restart || !S.pc) newPc();
  const offer = await S.pc.createOffer({ iceRestart: !!restart });
  await S.pc.setLocalDescription(offer);
  S.sig.send({ type: 'offer', sdp: offer.sdp, restart: !!restart });
}

async function onSignal(msg) {
  if (msg.type === 'peer-joined' && msg.role === 'caller') {
    $('waitState').textContent = 'Caller joined. Connecting…';
    makeOffer(false);
  } else if (msg.type === 'answer' && S.pc) {
    await S.pc.setRemoteDescription({ type: 'answer', sdp: msg.sdp });
  } else if (msg.type === 'ice' && S.pc) {
    try { await S.pc.addIceCandidate(msg.candidate); } catch {}
  } else if (msg.type === 'peer-left' || msg.type === 'bye') {
    setChip('connChip', 'bad', msg.type === 'bye' ? 'caller ended the call' : 'caller left — waiting');
  }
}

function enterCall() {
  if (!S.started) {
    S.started = Date.now();
    S.timer = setInterval(() => ($('timer').textContent = fmtTime(Math.floor((Date.now() - S.started) / 1000))), 1000);
  }
  show('waiting', false); show('call');
}

// ---------------------------------------------------------------- caller audio -> Prisma realtime
let callerSource = null, callerTap = null;
function attachCaller(stream) {
  $('callerAudio').srcObject = stream; // hear the caller (Chrome also needs this for WebAudio to receive remote audio)
  $('callerAudio').play().catch(() => {});
  if (callerSource) { try { callerSource.disconnect(); } catch {} }
  callerSource = S.ctx.createMediaStreamSource(stream);
  callerTap = callerTap || new AudioWorkletNode(S.ctx, 'pcm-tap');
  const sink = S.ctx.createGain(); sink.gain.value = 0; // pull the graph without playing it twice
  callerSource.connect(callerTap); callerTap.connect(sink); sink.connect(S.ctx.destination);
  callerTap.port.onmessage = (e) => onCallerPcm(e.data);
  S.ctx.resume();
  openLive();
}

function onCallerPcm(f32) {
  let peak = 0;
  for (let i = 0; i < f32.length; i++) peak = Math.max(peak, Math.abs(f32[i]));
  $('meter').style.width = Math.min(100, peak * 160) + '%';
  $('avatar').classList.toggle('talking', peak > 0.04);
  const i16 = floatToInt16(f32);
  S.callerPcm.push(i16); S.callerPcmLen += i16.length;
  if (S.callerPcmLen >= 512 && S.live && S.live.readyState === WebSocket.OPEN) {
    const out = new Int16Array(S.callerPcmLen);
    let o = 0; for (const c of S.callerPcm) { out.set(c, o); o += c.length; }
    S.callerPcm = []; S.callerPcmLen = 0;
    S.live.send(out.buffer);
    S.sentCallerFrames += 1;
  }
}

let liveAttempt = 0;
function openLive() {
  if (S.live && S.live.readyState <= 1) return;
  const ws = (S.live = new WebSocket(`${wsBase()}/ws/live/${S.sid}?language=${S.choice}&voice=${S.voice}`));
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => { liveAttempt = 0; };
  ws.onmessage = (e) => onLive(JSON.parse(e.data));
  ws.onclose = () => {
    if (S.ended) return;
    setChip('sttChip', 'amber', 'RUKO reconnecting…');
    setTimeout(openLive, Math.min(1000 * 2 ** ++liveAttempt, 8000));
  };
}

function onLive(m) {
  if (m.type === 'stt') {
    const map = { connected: ['ok', 'RUKO listening'], connecting: ['amber', 'RUKO connecting…'], reconnecting: ['amber', 'RUKO reconnecting…'], error: ['bad', 'RUKO transcription error'] };
    const [cls, txt] = map[m.state] || ['', m.state];
    setChip('sttChip', cls, txt + (m.state === 'error' && m.detail ? ` (${m.detail})` : ''));
  } else if (m.type === 'transcript') {
    addLine(m.speaker, m.text);
  } else if (m.type === 'risk') {
    setRisk(m.risk);
  } else if (m.type === 'alert') {
    addLine('RUKO', '⚠ ' + m.text);
    flashAlert(m.text);
    if (m.audio_url && S.voice) playRuko(m.audio_url);
  }
}

// ---------------------------------------------------------------- UI helpers
function setChip(id, cls, text) {
  const el = $(id);
  el.className = 'chip ' + (cls || '');
  const meter = id === 'callerChip' ? ' <span class="meter"><div id="meter"></div></span>' : '';
  el.innerHTML = `<i></i>${text}${meter}`;
}

function addLine(speaker, text) {
  const div = document.createElement('div');
  div.className = 'line ' + speaker;
  div.innerHTML = `<small>${speaker === 'CALLER' ? 'Caller' : speaker === 'USER' ? 'You (private)' : 'RUKO'}</small>`;
  div.appendChild(document.createTextNode(text));
  $('transcript').appendChild(div);
  $('transcript').scrollTop = $('transcript').scrollHeight;
}

function setRisk(r) {
  const changed = !S.risk || S.risk.level !== r.level;
  S.risk = r;
  $('risk').className = 'risk ' + r.level;
  $('riskLevel').textContent = LEVEL_LABEL[r.level];
  $('riskReason').textContent = r.reason_text;
  if (changed) $('risk').animate([{ transform: 'scale(1.03)' }, { transform: 'scale(1)' }], { duration: 300 });
}

let alertTimer = null;
function flashAlert(text) {
  $('alert').textContent = '⚠ ' + text;
  show('alert');
  clearTimeout(alertTimer);
  alertTimer = setTimeout(() => show('alert', false), 7000);
}

function setMicChip() {
  const live = S.callTrack && S.callTrack.enabled;
  const why = S.privateMode ? 'call mic muted (private)' : S.autoPaused ? 'call mic paused while RUKO speaks' : S.userMuted ? 'call mic muted' : 'call mic on';
  setChip('micChip', live ? 'ok' : 'bad', why);
  $('muteBtn').classList.toggle('on', S.userMuted);
}

async function checkHeadphones() {
  try {
    const outs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'audiooutput');
    const hp = outs.some((d) => /head|ear|bluetooth|buds|airpods|hands-?free|wired/i.test(d.label));
    show('hpWarn', !hp);
    if (HTMLMediaElement.prototype.setSinkId && outs.length > 1) {
      const sel = $('sink');
      sel.innerHTML = outs.map((d) => `<option value="${d.deviceId}">${d.label || 'Output ' + d.deviceId.slice(0, 4)}</option>`).join('');
      sel.onchange = () => ['callerAudio', 'rukoAudio'].forEach((id) => $(id).setSinkId(sel.value).catch(() => {}));
      show('sink');
    }
  } catch {}
}

// ---------------------------------------------------------------- call controls
$('muteBtn').onclick = () => {
  S.userMuted = !S.userMuted;
  if (!S.privateMode && !S.autoPaused) S.callTrack.enabled = !S.userMuted;
  setMicChip();
};

$('endBtn').onclick = () => {
  S.ended = true;
  try { S.sig.send({ type: 'bye' }); } catch {}
  stopRuko(); stopPrivateCapture(false);
  if (S.pc) S.pc.close();
  if (S.callTrack) S.callTrack.stop();
  if (S.live) S.live.close();
  if (S.sig) S.sig.close();
  clearInterval(S.timer);
  closeSheet(false);
  show('call', false); show('ended');
  const r = S.risk;
  $('endRisk').className = 'risk ' + (r ? r.level : 'INSUFFICIENT_INFORMATION');
  $('endRisk').innerHTML = r ? `<b>${LEVEL_LABEL[r.level]}</b><span>${r.reason_text}<br><br>${r.action_text}</span>` : '<b>NOT ENOUGH INFORMATION</b><span>No warning signs were heard.</span>';
};

// ---------------------------------------------------------------- RUKO voice (local only)
function playRuko(url) {
  const a = $('rukoAudio');
  a.src = url;
  $('callerAudio').volume = 0.25; // duck the caller so RUKO is clear
  if (!S.privateMode && S.callTrack.enabled) { S.callTrack.enabled = false; S.autoPaused = true; } // limit acoustic leak
  S.rukoPlaying = true; setMicChip();
  a.play().catch(() => onRukoDone());
  if (S.privateMode) setStatus('speaking');
}
function onRukoDone() {
  const a = $('rukoAudio');
  if (!a.paused && !a.ended) return; // late 'pause' from swapping src while a new clip plays
  S.rukoPlaying = false;
  $('callerAudio').volume = S.privateMode ? 0.35 : 1;
  if (S.autoPaused && !S.privateMode) { S.callTrack.enabled = !S.userMuted; }
  S.autoPaused = false;
  setMicChip();
  if (S.status === 'speaking') setStatus('idle');
}
$('rukoAudio').onended = onRukoDone;
$('rukoAudio').onpause = onRukoDone;
function stopRuko() { const a = $('rukoAudio'); if (!a.paused) a.pause(); }

// ---------------------------------------------------------------- private mode (RUKO sheet)
$('rukoBtn').onclick = openSheet;
$('backBtn').onclick = () => closeSheet(true);

function openSheet() {
  S.privateMode = true;
  S.callTrack.enabled = false; // caller now receives silence; the connection stays up
  $('callerAudio').volume = 0.35;
  setMicChip();
  show('sheetWrap');
  renderLangs();
  setStatus(S.status);
}

/** Explicit return to the call: stop private capture/playback, restore call mic. */
function closeSheet(restore) {
  stopPrivateCapture(false);
  stopRuko();
  S.privateMode = false;
  if (restore && S.callTrack) S.callTrack.enabled = !S.userMuted;
  $('callerAudio').volume = 1;
  setMicChip();
  show('sheetWrap', false);
}

function renderLangs() {
  $('langBtn').textContent = LANGS.find((l) => l[0] === S.choice)[1];
  $('langs').innerHTML = '';
  for (const [code, label] of LANGS) {
    const b = document.createElement('button');
    b.textContent = label; b.className = code === S.choice ? 'on' : '';
    b.onclick = () => {
      S.choice = code; show('langs', false); renderLangs(); setStatus(S.status);
      if (S.live && S.live.readyState === 1) S.live.send(JSON.stringify({ type: 'settings', language: code }));
    };
    $('langs').appendChild(b);
  }
}
$('langBtn').onclick = () => $('langs').classList.toggle('hidden');

$('voiceToggle').onchange = (e) => {
  S.voice = e.target.checked;
  if (!S.voice) stopRuko();
  if (S.live && S.live.readyState === 1) S.live.send(JSON.stringify({ type: 'settings', voice: S.voice }));
};

function ui() { const l = S.choice === 'auto' ? S.lang : S.choice; return UI[l] || (l === 'hi-en' ? UI.en : UI.en); }
function setStatus(st) {
  S.status = st;
  const t = ui();
  $('status').textContent = { idle: t.tap, listening: t.listening, transcribing: t.transcribing, thinking: t.thinking, speaking: t.speaking }[st];
  $('textIn').placeholder = t.type;
  $('micBtn').className = 'mic' + (st === 'listening' ? ' rec' : st === 'speaking' ? ' speak' : '');
  $('micBtn').textContent = st === 'listening' ? '■' : st === 'speaking' ? '🔊' : st === 'idle' ? '🎤' : '…';
  $('micBtn').disabled = st === 'transcribing' || st === 'thinking';
}

function sheetError(msg) { $('sheetErr').textContent = msg; show('sheetErr', !!msg); }

function addConvo(kind, text) {
  document.querySelectorAll('#convo .r.latest').forEach((n) => n.classList.remove('latest'));
  const d = document.createElement('div');
  d.className = kind === 'u' ? 'u' : 'r latest';
  d.textContent = text;
  $('convo').appendChild(d);
  $('convo').scrollTop = $('convo').scrollHeight;
}

$('micBtn').onclick = () => {
  if (S.status === 'listening') return S.privateStop && S.privateStop(true);
  if (S.status === 'speaking') { stopRuko(); return setStatus('idle'); }
  if (S.status === 'idle') startPrivateCapture();
};

/** Private mic = a SECOND getUserMedia track, never added to the peer connection. */
async function startPrivateCapture() {
  sheetError('');
  stopRuko();
  let track;
  try {
    const st = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
    track = st.getAudioTracks()[0];
  } catch (e) { return sheetError(micErrorText(e)); }
  S.privateTrack = track;
  const src = S.ctx.createMediaStreamSource(new MediaStream([track]));
  const tap = new AudioWorkletNode(S.ctx, 'pcm-tap');
  const sink = S.ctx.createGain(); sink.gain.value = 0;
  src.connect(tap); tap.connect(sink); sink.connect(S.ctx.destination);
  const chunks = []; const t0 = Date.now();
  tap.port.onmessage = (e) => chunks.push(floatToInt16(e.data));
  setStatus('listening');
  const auto = setTimeout(() => S.privateStop && S.privateStop(true), 28000);
  S.privateStop = async (send) => {
    clearTimeout(auto);
    S.privateStop = null;
    try { src.disconnect(); tap.disconnect(); sink.disconnect(); } catch {}
    track.stop(); S.privateTrack = null;
    if (!send) return setStatus('idle');
    if (Date.now() - t0 < 700) { setStatus('idle'); return sheetError('That was too short. Tap the mic and speak a little longer.'); }
    setStatus('transcribing');
    try {
      const b64 = await blobToBase64(encodeWav(chunks));
      const r = await fetch('/turn/voice64', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: S.sid, audio_b64: b64, ext: 'wav', language: S.choice }) });
      await handleTurn(r, true);
    } catch { failTurn(); }
  };
  S.ctx.resume();
}
function stopPrivateCapture(send) { if (S.privateStop) S.privateStop(send); }

async function sendText() {
  const text = $('textIn').value.trim();
  if (!text || S.status !== 'idle' && S.status !== 'speaking') return;
  stopRuko(); sheetError('');
  $('textIn').value = '';
  addConvo('u', text); addLine('USER', text);
  setStatus('thinking');
  try {
    const r = await fetch('/turn/text', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: S.sid, text, language: S.choice }) });
    await handleTurn(r, false);
  } catch { failTurn(); }
}
$('sendBtn').onclick = sendText;
$('textIn').onkeydown = (e) => e.key === 'Enter' && sendText();

async function handleTurn(r, fromVoice) {
  const j = await r.json();
  if (!r.ok) {
    setStatus('idle');
    const err = j.error || j.detail || {};
    return sheetError(err.code === 'EMPTY_AUDIO' ? "I couldn't hear anything. Please try again." : err.message || 'Something went wrong. Please try again.');
  }
  if (fromVoice && j.transcript) { addConvo('u', j.transcript); addLine('USER', j.transcript); }
  S.lang = j.language;
  addConvo('r', j.reply_text);
  setRisk(j.risk);
  if (j.audio_url) playRuko(j.audio_url);
  else { setStatus('idle'); sheetError('Voice unavailable right now — the answer is shown above.'); }
}
function failTurn() { setStatus('idle'); sheetError('Cannot reach the RUKO server. Check your connection and try again.'); }

// ---------------------------------------------------------------- test / isolation hook
window.__ruko = {
  S,
  isolation() {
    const senders = S.pc ? S.pc.getSenders().map((s) => s.track && { id: s.track.id, enabled: s.track.enabled, label: s.track.label }) : [];
    return {
      senderTrackIds: senders.filter(Boolean).map((t) => t.id),
      callTrackId: S.callTrack && S.callTrack.id,
      callTrackEnabled: S.callTrack && S.callTrack.enabled,
      privateTrackId: S.privateTrack && S.privateTrack.id,
      privateInSenders: !!(S.privateTrack && senders.some((t) => t && t.id === S.privateTrack.id)),
      privateMode: S.privateMode,
      rukoPlaying: S.rukoPlaying,
      sentCallerFrames: S.sentCallerFrames,
    };
  },
  openSheet, closeSheet, startPrivateCapture, stopPrivateCapture,
};

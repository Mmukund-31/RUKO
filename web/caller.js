// Caller side of the demo call: answers the RUKO user's offer, sends its mic, plays the user's audio.
import { Signal, rtcConfig, getCallMic, micErrorText, fmtTime } from './rtc.js';

const $ = (id) => document.getElementById(id);
const room = location.pathname.split('/').pop().toUpperCase();
$('room').textContent = room;

let pc = null, track = null, sig = null, started = 0, timer = null, cfg = null;
const state = { muted: false, conn: 'new' };

function setConn(s) {
  state.conn = s;
  const el = $('conn');
  el.className = 'chip ' + (s === 'connected' ? 'ok' : s === 'failed' || s === 'disconnected' ? 'bad' : 'amber');
  el.innerHTML = `<i></i>${s}`;
  if (s === 'connected' && !timer) {
    started = Date.now();
    timer = setInterval(() => ($('timer').textContent = fmtTime(Math.floor((Date.now() - started) / 1000))), 1000);
  }
}

function newPc() {
  if (pc) pc.close();
  pc = new RTCPeerConnection(cfg);
  pc.addTrack(track, new MediaStream([track]));
  pc.onicecandidate = (e) => e.candidate && sig.send({ type: 'ice', candidate: e.candidate });
  pc.ontrack = (e) => { $('remote').srcObject = e.streams[0] || new MediaStream([e.track]); };
  pc.onconnectionstatechange = () => setConn(pc.connectionState);
  return pc;
}

async function onSignal(msg) {
  if (msg.type === 'offer') {
    if (!pc || !msg.restart) newPc();
    await pc.setRemoteDescription({ type: 'offer', sdp: msg.sdp });
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    sig.send({ type: 'answer', sdp: answer.sdp });
  } else if (msg.type === 'ice' && pc) {
    try { await pc.addIceCandidate(msg.candidate); } catch {}
  } else if (msg.type === 'bye') {
    if (pc) { pc.onconnectionstatechange = null; pc.close(); pc = null; }
    setConn('ended by user');
    clearInterval(timer);
  } else if (msg.type === 'peer-left') {
    if (!/ended/.test(state.conn)) setConn('user left — waiting');
  }
}

$('join').onclick = async () => {
  $('err').classList.add('hidden');
  try {
    track = await getCallMic();
  } catch (e) {
    $('err').textContent = micErrorText(e);
    $('err').classList.remove('hidden');
    return;
  }
  cfg = await rtcConfig();
  $('pre').classList.add('hidden');
  $('call').classList.remove('hidden');
  setConn('waiting for user');
  sig = new Signal(room, 'caller', {
    onMessage: onSignal,
    onState: (s) => { if (s === 'no-room') { $('err').textContent = 'This room does not exist or has expired.'; $('pre').classList.remove('hidden'); $('err').classList.remove('hidden'); } },
  });
};

$('mute').onclick = () => {
  state.muted = !state.muted;
  if (track) track.enabled = !state.muted;
  $('mute').classList.toggle('on', state.muted);
  $('micchip').className = 'chip ' + (state.muted ? 'bad' : 'ok');
  $('micchip').innerHTML = `<i></i>${state.muted ? 'mic muted' : 'mic on'}`;
};

$('end').onclick = () => {
  if (sig) sig.send({ type: 'bye' });
  if (pc) pc.close();
  if (track) track.stop();
  if (sig) sig.close();
  setConn('ended');
  clearInterval(timer);
};

// Test hook: inbound audio energy from the RUKO user (used to verify private-mode isolation).
window.__caller = {
  state,
  async inboundEnergy() {
    if (!pc) return null;
    let e = null;
    (await pc.getStats()).forEach((r) => { if (r.type === 'inbound-rtp' && r.kind === 'audio') e = { energy: r.totalAudioEnergy, level: r.audioLevel, packets: r.packetsReceived }; });
    return e;
  },
};

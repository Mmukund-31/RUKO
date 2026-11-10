// Two-browser live-call test: REAL WebRTC, REAL Gnani Prisma (realtime + REST) and Timbre.
// Two separate browser processes, each with a fake microphone fed by a synthetic Timbre WAV:
//   caller browser: reads the bank-OTP scam script      (fixtures/caller.wav)
//   user browser:   asks RUKO a Telugu question         (fixtures/user.wav)
// Checks: call connects, caller speech is transcribed (CALLER), risk becomes HIGH, a Timbre alert
// arrives, and audio isolation: while in private mode (and while RUKO speaks) the caller receives
// no audio energy from the user; after "Back to call" audio flows again.
//
// Usage: node live_call.e2e.mjs [http://localhost:8000] [chrome|msedge]
import { chromium } from 'playwright-core';
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const BASE = process.argv[2] || 'http://localhost:8000';
const CHANNEL = process.argv[3] || 'chrome';
const fx = (f) => resolve('fixtures', f);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = { checks: [], transcripts: [], alerts: [], private_reply: null };
const check = (name, ok, detail) => { results.checks.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail !== undefined ? '  ' + JSON.stringify(detail) : ''}`); };

const args = (wav) => [
  '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
  `--use-file-for-fake-audio-capture=${wav}`, '--autoplay-policy=no-user-gesture-required',
  ...(BASE.startsWith('https') ? ['--ignore-certificate-errors'] : []), // self-signed LAN cert
];

const userB = await chromium.launch({ channel: CHANNEL, headless: true, args: args(fx('user.wav')) });
const callerB = await chromium.launch({ channel: CHANNEL, headless: true, args: args(fx('caller.wav')) });
const ctxOpts = { ignoreHTTPSErrors: BASE.startsWith('https') };
const user = await (await userB.newContext(ctxOpts)).newPage();
const caller = await (await callerB.newContext(ctxOpts)).newPage();
user.on('console', (m) => m.type() === 'error' && console.log('[user console]', m.text()));
caller.on('console', (m) => m.type() === 'error' && console.log('[caller console]', m.text()));

async function energyDelta(ms) {
  const a = await caller.evaluate(() => window.__caller.inboundEnergy());
  await sleep(ms);
  const b = await caller.evaluate(() => window.__caller.inboundEnergy());
  return a && b ? +(b.energy - a.energy).toFixed(6) : null;
}

try {
  // 1. user starts a call, caller joins via the room link
  await user.goto(BASE + '/');
  await user.click('#startBtn');
  await user.waitForSelector('#joinUrl:not(:empty)');
  const room = await user.textContent('#roomId');
  check('room created', /^[A-Z0-9]{6}$/.test(room), room);
  await caller.goto(`${BASE}/join/${room}`);
  await caller.click('#join');
  await user.waitForSelector('#call:not(.hidden)', { timeout: 20000 });
  check('WebRTC connected (user side)', (await user.textContent('#connChip')).includes('connected'));
  await caller.waitForFunction(() => document.getElementById('conn').textContent.includes('connected'), null, { timeout: 15000 });
  check('WebRTC connected (caller side)', true);

  // 2. caller speech -> Prisma realtime -> CALLER transcript -> HIGH -> Timbre alert
  await user.waitForFunction(() => document.querySelectorAll('.line.CALLER').length >= 1, null, { timeout: 45000 });
  await user.waitForFunction(() => document.getElementById('risk').classList.contains('HIGH_RISK'), null, { timeout: 60000 });
  await user.waitForFunction(() => [...document.querySelectorAll('.line.RUKO')].some((n) => /OTP/.test(n.textContent)), null, { timeout: 30000 });
  results.transcripts = await user.$$eval('.line.CALLER', (ns) => ns.map((n) => n.lastChild.textContent));
  results.alerts = await user.$$eval('.line.RUKO', (ns) => ns.map((n) => n.lastChild.textContent));
  check('caller speech transcribed by Prisma (CALLER lines)', results.transcripts.length > 0, results.transcripts);
  check('risk reached HIGH from caller statements', true, await user.textContent('#riskReason'));
  await user.screenshot({ path: 'out/user_call.png' });
  await caller.screenshot({ path: 'out/caller_call.png' });
  check('spoken alert generated (Timbre)', results.alerts.some((t) => /OTP/.test(t)), results.alerts);
  const iso0 = await user.evaluate(() => window.__ruko.isolation());
  check('only the call track is sent to the caller', iso0.senderTrackIds.length === 1 && iso0.senderTrackIds[0] === iso0.callTrackId, iso0);
  check('caller audio frames streamed to RUKO', iso0.sentCallerFrames > 50, iso0.sentCallerFrames);

  // 3. normal call: user's mic reaches the caller
  await user.waitForFunction(() => !window.__ruko.isolation().rukoPlaying, null, { timeout: 30000 });
  const eNormal = await energyDelta(3000);
  check('normal mode: caller receives the user\'s voice', eNormal > 0.001, eNormal);

  // 4. private mode: call track disabled, caller gets silence; private mic is a separate track
  await user.click('#rukoBtn');
  await sleep(800);
  const iso1 = await user.evaluate(() => window.__ruko.isolation());
  check('private mode: call track disabled', iso1.callTrackEnabled === false && iso1.privateMode, iso1);
  const ePrivate = await energyDelta(3000);
  check('private mode: caller receives no user audio', ePrivate !== null && ePrivate < eNormal * 0.05, ePrivate);

  await user.click('#micBtn'); // start private capture (second getUserMedia track)
  await sleep(600);
  const iso2 = await user.evaluate(() => window.__ruko.isolation());
  check('private mic is a different track, not in any sender', !!iso2.privateTrackId && iso2.privateTrackId !== iso2.callTrackId && !iso2.privateInSenders, iso2);
  const eRecording = await energyDelta(6200);
  check('while recording privately: caller receives no user audio', eRecording < eNormal * 0.05, eRecording);
  await user.click('#micBtn'); // stop -> WAV -> /turn/voice64 -> Prisma REST -> reply -> Timbre
  await user.waitForFunction(() => document.querySelectorAll('#convo .r').length >= 1, null, { timeout: 45000 });
  results.private_reply = {
    heard: await user.$$eval('#convo .u', (ns) => ns.map((n) => n.textContent)),
    reply: await user.$eval('#convo .r.latest', (n) => n.textContent),
  };
  check('user private speech transcribed (USER) and answered with caller context', results.private_reply.heard.length > 0, results.private_reply);
  const playing = await user.waitForFunction(() => window.__ruko.isolation().rukoPlaying, null, { timeout: 15000 }).then(() => true).catch(() => false);
  check('RUKO reply is playing locally', playing);
  await user.screenshot({ path: 'out/user_private.png' });
  const eRuko = await energyDelta(2500);
  check('while RUKO speaks: caller receives no RUKO/user audio', eRuko < eNormal * 0.05, eRuko);

  // 5. explicit return to call restores the call mic
  await user.click('#backBtn');
  await sleep(800);
  const iso3 = await user.evaluate(() => window.__ruko.isolation());
  check('back to call: call track re-enabled', iso3.callTrackEnabled === true && !iso3.privateMode, iso3);
  const eBack = await energyDelta(3000);
  check('back to call: caller hears the user again', eBack > 0.001, eBack);

  // 6. transcripts stayed separated by speaker on the server
  const sid = await user.evaluate(() => window.__ruko.S.sid);
  const log = await user.evaluate(async (sid) => (await fetch(`/session/${sid}/transcript`)).json(), sid);
  const speakers = [...new Set(log.transcripts.map((t) => t.speaker))];
  check('server transcript log has separate CALLER and USER records', speakers.includes('CALLER') && speakers.includes('USER'), log.transcripts.map((t) => `${t.speaker}: ${t.text}`));

  // 7. end call
  await user.click('#endBtn');
  await caller.waitForFunction(() => /ended|left/.test(document.getElementById('conn').textContent), null, { timeout: 10000 });
  check('call termination reaches the caller', true, await caller.textContent('#conn'));
  await user.screenshot({ path: 'out/user_end.png' });
} catch (e) {
  check('unexpected error', false, String(e).slice(0, 500));
  await user.screenshot({ path: 'out/user_fail.png' }).catch(() => {});
  await caller.screenshot({ path: 'out/caller_fail.png' }).catch(() => {});
} finally {
  writeFileSync('out/live_call_results.json', JSON.stringify(results, null, 2));
  await userB.close(); await callerB.close();
}
const failed = results.checks.filter((c) => !c.ok).length;
console.log(`\n${results.checks.length - failed}/${results.checks.length} checks passed`);
process.exit(failed ? 1 : 0);

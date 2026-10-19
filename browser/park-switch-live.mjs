// Private Chromium gameplay capture for an A -> B park transition.
import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const url = process.env.WASM_LIVE_URL || 'http://127.0.0.1:8091/';
const profile = process.env.WASM_LIVE_PROFILE || path.join(root, 'run-data/park-switch-browser-profile');
const target = process.env.PARK_SWITCH_TARGET || 'frontier-outpost-playable.park';
const decision = process.env.PARK_SWITCH_DECISION || 'discard';
const suffix = decision === 'save' ? '-save' : '';
const artifacts = path.join(root, `run-data/verification/browser-park-switch${suffix}`);
const resultPath = path.join(root, `run-data/verification/browser-park-switch${suffix}.json`);
const report = { result: 'failed', url, target, decision, started_at: new Date().toISOString(), events: [] };
let context;
let page;
let screencast;
let statusTimer;
const frameWrites = [];
let frameCount = 0;
await mkdir(artifacts, { recursive: true });
try {
  const parkProbe = `var PARK_SWITCH_PROBE_TARGET = ${JSON.stringify(target)};\n`
    + `var PARK_SWITCH_PROBE_DECISION = ${JSON.stringify(decision)};\n` +
    'var PARK_SWITCH_PROBE_DELAY_MS = 30000;\n' +
    await readFile(path.join(root, 'browser/park-switch-probe.js'), 'utf8');
  const defenseProbe = 'var UNIVERSAL_DEFENSE_ANCHOR = [44, 56];\n' +
    'var UNIVERSAL_DEFENSE_VERIFY_BUILD = true;\n' +
    'var UNIVERSAL_DEFENSE_VERIFY_MANUAL = true;\n' +
    await readFile(path.join(root, 'tests/universal-defense-probe.js'), 'utf8');
  context = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    viewport: { width: 1280, height: 800 },
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  page = await context.newPage();
  await page.addInitScript(({ parkProbe, defenseProbe }) => {
    Object.defineProperty(window, 'Module', { configurable: true, set(module) {
      Object.defineProperty(window, 'Module', { value: module, configurable: true });
      const original = module.callMain.bind(module);
      module.callMain = (args) => {
        module.FS.mkdirTree('/persistent/plugin');
        module.FS.writeFile('/persistent/plugin/park-switch-probe.js', parkProbe);
        module.FS.writeFile('/persistent/plugin/universal-defense-probe.js', defenseProbe);
        original(args);
      };
    } });
  }, { parkProbe, defenseProbe });
  const waiters = [];
  const waitFor = (pattern, timeout = 300000) => new Promise((resolve, reject) => {
    const previous = report.events.find((event) => event.line && pattern.test(event.line));
    if (previous) { resolve(previous.line); return; }
    const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${pattern}`)), timeout);
    waiters.push({ pattern, resolve: (line) => { clearTimeout(timer); resolve(line); } });
  });
  page.on('console', (message) => {
    const line = message.text();
    if (/PARK_SWITCH_|UNIVERSAL_DEFENSE_|WORLD_SCENARIO_STATUS|WORLD_READY/.test(line)) {
      report.events.push({ at: new Date().toISOString(), line });
      console.log(line);
    }
    if (/error|failed|plugin|network|socket/i.test(line) && !/Paint.Entity.cpp/.test(line))
      console.log(`CLIENT: ${line}`);
    for (const waiter of waiters.slice()) if (waiter.pattern.test(line)) {
      waiters.splice(waiters.indexOf(waiter), 1);
      waiter.resolve(line);
    }
  });
  page.on('pageerror', (error) => {
    report.events.push({ at: new Date().toISOString(), error: error.message });
    console.log(`PAGE_ERROR: ${error.message}`);
  });
  page.on('requestfailed', (request) => console.log(`REQUEST_FAILED: ${request.url()}`));
  page.on('websocket', (socket) => console.log(`WEBSOCKET: ${socket.url()}`));
  const initial = await (await context.request.get(new URL('/private/park-session', url).href)).json();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  console.log('PAGE_GOTO_OK');
  let lastStatus = '';
  statusTimer = setInterval(async () => {
    try {
      const state = await page.evaluate(() => ({
        message: document.getElementById('message')?.textContent || '',
        canvas: document.getElementById('canvas')?.style.display || '',
        error: document.getElementById('status')?.classList.contains('error') || false,
      }));
      const summary = JSON.stringify(state);
      if (summary !== lastStatus) {
        lastStatus = summary;
        console.log(`BROWSER_STATUS: ${summary}`);
      }
    } catch (_) {}
  }, 10000);
  await waitFor(/PARK_SWITCH_BROWSER_READY park=.*generation=/, 420000);
  const before = await page.evaluate(async () => (await fetch('/private/park-session')).json());
  report.before = before;
  if (before.phase !== 'ready' || before.current === target) throw new Error('Expected an active Park A');
  const frames = path.join(artifacts, 'frames');
  await rm(frames, { recursive: true, force: true });
  await mkdir(frames, { recursive: true });
  screencast = await context.newCDPSession(page);
  screencast.on('Page.screencastFrame', ({ data, sessionId }) => {
    if (frameCount < 400) {
      frameCount++;
      frameWrites.push(writeFile(path.join(frames, `frame-${String(frameCount).padStart(4, '0')}.jpg`),
        Buffer.from(data, 'base64')));
    }
    screencast.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
  });
  await screencast.send('Page.startScreencast', { format: 'jpeg', quality: 70,
    maxWidth: 1280, maxHeight: 800, everyNthFrame: 15 });
  await page.locator('#canvas').focus();
  await page.mouse.move(640, 400);
  await page.keyboard.press('Control+Shift+L');
  await waitFor(/PARK_SWITCH_MENU_VISIBLE/, 15000);
  await page.screenshot({ path: path.join(artifacts, 'park-a-menu.png') });
  const beforeUnits = await waitFor(/PARK_SWITCH_BROWSER_BEFORE units=/, 300000);
  const actorCount = Number(/units=(\d+)/.exec(beforeUnits)?.[1] || 0);
  report.actor_count_before_switch = actorCount;
  if (actorCount < 1) throw new Error('No StarCraft units were visible before switching parks');
  await page.screenshot({ path: path.join(artifacts, 'park-a-units.png') });
  const afterReady = await waitFor(new RegExp(`PARK_SWITCH_BROWSER_READY park=${target.replaceAll('.', '\\.')}`), 420000);
  const afterUnits = Number(/units=(\d+)/.exec(afterReady)?.[1]);
  report.actor_count_after_switch = afterUnits;
  if (afterUnits !== 0) throw new Error(`Fresh park had ${afterUnits} surviving StarCraft units`);
  const after = await page.evaluate(async () => (await fetch('/private/park-session')).json());
  report.after = after;
  if (after.phase !== 'ready' || after.current !== target || after.generation === before.generation)
    throw new Error('Browser did not reconnect to a new Park B generation');
  await page.screenshot({ path: path.join(artifacts, 'park-b-ready.png') });
  await screencast.send('Page.stopScreencast');
  await Promise.all(frameWrites);
  if (frameCount < 2) throw new Error('Chromium did not emit enough gameplay frames');
  const video = path.join(artifacts, 'park-a-to-b.webm');
  await new Promise((resolve, reject) => {
    const encoding = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', '2',
      '-i', path.join(frames, 'frame-%04d.jpg'), '-c:v', 'libvpx-vp9',
      '-pix_fmt', 'yuv420p', video]);
    encoding.on('error', reject);
    encoding.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`FFmpeg exited ${code}`)));
  });
  report.result = 'passed';
  report.initial = initial;
  report.video = video;
  report.frames = frameCount;
} catch (error) {
  report.error = String(error?.stack || error);
  if (page) await page.screenshot({ path: path.join(artifacts, 'startup-failure.png') }).catch(() => {});
  throw error;
} finally {
  if (statusTimer) clearInterval(statusTimer);
  if (screencast) await screencast.send('Page.stopScreencast').catch(() => {});
  if (context) await context.close();
  await writeFile(resultPath, JSON.stringify(report, null, 2) + '\n');
  console.log(`PARK_SWITCH_RESULT ${report.result} ${resultPath}`);
}

// Capture a Chromium OpenRCT2 client against a running native StarCoaster host.
// Licensed RCT2 files must already have been imported at this origin/profile.
import { chromium } from 'playwright-core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = path.join(root, 'build', 'wasm-live-test');
const profile = process.env.WASM_LIVE_PROFILE || path.join(root, 'build', 'wasm-browser-test', 'chromium-live-profile');
const url = process.env.WASM_LIVE_URL || 'http://127.0.0.1:8091/';
const durationMs = Number(process.env.WASM_LIVE_DURATION_MS || 45000);
let selection = [process.env.WASM_CLICK_X, process.env.WASM_CLICK_Y].map(Number);
let order = [process.env.WASM_ORDER_X, process.env.WASM_ORDER_Y].map(Number);
let haveSelection = process.env.WASM_CLICK_X !== undefined && process.env.WASM_CLICK_Y !== undefined;
let haveOrder = process.env.WASM_ORDER_X !== undefined && process.env.WASM_ORDER_Y !== undefined;
const cameraProbe = process.env.WASM_LIVE_CAMERA === '1';
const autoOrder = process.env.WASM_AUTO_ORDER === '1';
const cameraSweep = process.env.WASM_CAMERA_SWEEP === '1';
const secondOrderDelayMs = Number(process.env.WASM_SECOND_ORDER_DELAY_MS || 0);
const captureIntervalMs = Number(process.env.WASM_CAPTURE_INTERVAL_MS || 30000);
const records = [];
const metrics = { origin: url, startedAt: new Date().toISOString(), websocketFramesIn: 0,
  websocketFramesOut: 0, websocketBytesIn: 0, websocketBytesOut: 0, workers: 0 };
let outcome = 'failed';
let context;
let statusTimer;
const capture = (page, filename) => page.screenshot({
  path: path.join(artifacts, filename), timeout: 120000,
});

await mkdir(artifacts, { recursive: true });
try {
  context = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    viewport: { width: 1280, height: 800 },
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await context.newPage();
  let lastStatus = '';
  statusTimer = setInterval(async () => {
    try {
      const status = await page.evaluate(() => document.getElementById('message')?.textContent ||
        (document.getElementById('canvas')?.style.display === 'block' ? 'OpenRCT2 canvas running' : ''));
      if (status && status !== lastStatus) {
        lastStatus = status;
        console.log(`STATUS: ${status}`);
      }
    } catch (_) {}
  }, 5000);
  if (cameraProbe) {
    const source = await readFile(path.join(root, 'browser', 'live-camera.js'), 'utf8');
    const cameraSource = cameraSweep ? 'var STARCOASTER_CAMERA_SWEEP = true;\n' + source : source;
    await page.addInitScript((source) => {
      Object.defineProperty(window, 'Module', {
        configurable: true,
        set(module) {
          Object.defineProperty(window, 'Module', { value: module, configurable: true });
          const original = module.callMain.bind(module);
          module.callMain = (args) => {
            module.FS.mkdirTree('/persistent/plugin');
            module.FS.writeFile('/persistent/plugin/wasm-live-camera.js', source);
            original(args);
          };
        },
      });
    }, cameraSource);
  }
  let resolveCamera;
  const cameraReady = new Promise((resolve) => { resolveCamera = resolve; });
  let resolveActorScreen;
  const actorScreenReady = new Promise((resolve) => { resolveActorScreen = resolve; });
  page.on('console', (message) => {
    const line = message.text();
    records.push({ kind: 'console', text: line, at: Date.now() });
    if (line.includes('WASM_CAMERA_READY')) resolveCamera();
    const screen = /WASM_ACTOR_SCREEN id=([^ ]+) x=([\d.]+) y=([\d.]+)/.exec(line);
    if (screen) resolveActorScreen({ id: screen[1], x: Number(screen[2]), y: Number(screen[3]) });
    if (line.includes('WASM_ACTOR_MOVED') && metrics.orderSentAt && metrics.actorMoveLatencyMs === undefined)
      metrics.actorMoveLatencyMs = Date.now() - metrics.orderSentAt;
    if (line.includes('WASM_ACTOR_MOVED') && metrics.secondOrderSentAt &&
      metrics.secondActorMoveLatencyMs === undefined)
      metrics.secondActorMoveLatencyMs = Date.now() - metrics.secondOrderSentAt;
    if (/index|network|plugin|WORLD_|RTS Bridge|WASM_CAMERA|WASM_ACTOR|Failed to connect/i.test(line))
      console.log(`CLIENT: ${line}`);
  });
  page.on('pageerror', (error) => records.push({ kind: 'pageerror', text: error.message }));
  page.on('worker', () => metrics.workers++);
  page.on('websocket', (socket) => {
    records.push({ kind: 'websocket', url: socket.url() });
    console.log(`WEBSOCKET: ${socket.url()}`);
    socket.on('framereceived', (frame) => {
      metrics.websocketFramesIn++;
      metrics.websocketBytesIn += Buffer.byteLength(frame.payload);
    });
    socket.on('framesent', (frame) => {
      metrics.websocketFramesOut++;
      metrics.websocketBytesOut += Buffer.byteLength(frame.payload);
    });
    socket.on('socketerror', (error) => records.push({ kind: 'websocketerror', text: String(error) }));
    socket.on('close', () => records.push({ kind: 'websocketclose', url: socket.url() }));
  });
  const start = Date.now();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() =>
    document.getElementById('canvas')?.style.display === 'block' ||
    document.getElementById('status')?.classList.contains('error'),
  null, { timeout: 180000 });
  if (await page.locator('#status.error').count())
    throw new Error(await page.locator('#status.error #message').textContent());
  metrics.canvasMs = Date.now() - start;
  if (cameraProbe) {
    let timeout;
    try {
      await Promise.race([cameraReady, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error('The live camera did not observe a Marine snapshot')), 420000);
      })]);
    } finally { clearTimeout(timeout); }
    const mixedClientDelayMs = Number(process.env.WASM_MIXED_CLIENT_DELAY_MS || 0);
    if (mixedClientDelayMs > 0) {
      console.log(`MIXED_CLIENT_WAIT: ${mixedClientDelayMs} ms`);
      await page.waitForTimeout(mixedClientDelayMs);
    }
  } else {
    await page.waitForTimeout(15000);
  }
  const frameSample = await page.evaluate(() => new Promise((resolve) => {
    const started = performance.now();
    let frames = 0;
    function frame(now) {
      frames++;
      if (now - started >= 5000) resolve({ frames, ms: now - started });
      else requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }));
  metrics.animationFrameFps = Math.round(frameSample.frames * 1000 / frameSample.ms * 10) / 10;
  metrics.canvas = await page.evaluate(() => {
    const canvas = document.getElementById('canvas');
    const rect = canvas.getBoundingClientRect();
    return { width: canvas.width, height: canvas.height, clientWidth: rect.width,
      clientHeight: rect.height, left: rect.left, top: rect.top, devicePixelRatio };
  });
  console.log(`CANVAS: ${JSON.stringify(metrics.canvas)}`);
  await capture(page, 'connected.png');
  if (autoOrder) {
    if (!cameraProbe) throw new Error('WASM_AUTO_ORDER requires WASM_LIVE_CAMERA=1');
    let timeout;
    let screen;
    try {
      screen = await Promise.race([actorScreenReady, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error('No visible Marine screen coordinate')), 30000);
      })]);
    } finally { clearTimeout(timeout); }
    selection = [screen.x, screen.y - 8];
    order = [screen.x + 20, screen.y + 80];
    haveSelection = true;
    haveOrder = true;
    metrics.actorId = screen.id;
    metrics.selectionPoint = selection;
    metrics.orderPoint = order;
  }
  if (haveSelection) {
    metrics.selectionSentAt = Date.now();
    const candidates = autoOrder ? [selection,
      [selection[0], selection[1] + 8],
      [selection[0] / 2, selection[1] / 2],
      [selection[0] / 2, selection[1] / 2 + 8]] : [selection];
    for (const point of candidates) {
      await page.mouse.click(...point);
      await page.waitForTimeout(800);
      console.log(`CLICK: ${JSON.stringify(point)}`);
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes(`RTS Bridge selected units=${metrics.actorId}`))) {
        selection = point;
        break;
      }
    }
    await capture(page, 'selected.png');
  }
  if (haveOrder) {
    if (!haveSelection) throw new Error('An order needs WASM_CLICK_X and WASM_CLICK_Y');
    const candidates = autoOrder ? [order,
      [order[0] - 100, order[1]],
      [order[0] + 80, order[1] - 35]] : [order];
    for (const point of candidates) {
      metrics.orderPoint = point;
      metrics.orderSentAt = Date.now();
      await page.mouse.click(...point, { button: 'right' });
      console.log(`ORDER: ${JSON.stringify(point)}`);
      await page.waitForTimeout(3500);
      if (metrics.actorMoveLatencyMs !== undefined) break;
    }
    await capture(page, 'ordered.png');
  }
  if (secondOrderDelayMs > 0) {
    if (!autoOrder || metrics.actorMoveLatencyMs === undefined)
      throw new Error('A second order requires a successful first browser order');
    console.log(`SECOND_ORDER_WAIT: ${secondOrderDelayMs} ms`);
    await page.waitForTimeout(secondOrderDelayMs);
    const secondCandidates = [[selection[0], selection[1] + 8],
      [selection[0] - 80, selection[1] + 88]];
    for (const point of secondCandidates) {
      metrics.secondOrderPoint = point;
      metrics.secondOrderSentAt = Date.now();
      await page.mouse.click(...point, { button: 'right' });
      console.log(`SECOND_ORDER: ${JSON.stringify(point)}`);
      await page.waitForTimeout(5000);
      if (metrics.secondActorMoveLatencyMs !== undefined) break;
    }
    await capture(page, 'second-ordered.png');
  }
  for (let elapsed = 0; elapsed < durationMs; elapsed += captureIntervalMs) {
    const step = Math.min(captureIntervalMs, durationMs - elapsed);
    await page.waitForTimeout(step);
    await capture(page, `progress-${elapsed + step}.png`);
    console.log(`PROGRESS: ${elapsed + step} ms, ${metrics.websocketFramesIn} inbound frames`);
  }
  await capture(page, 'final.png');
  metrics.elapsedMs = Date.now() - start;
  metrics.heapBytes = await page.evaluate(() => performance.memory?.usedJSHeapSize ?? null);
  metrics.crossOriginIsolated = await page.evaluate(() => crossOriginIsolated);
  if (!metrics.websocketFramesIn || !metrics.websocketFramesOut)
    throw new Error('The browser did not exchange native multiplayer frames over /ws');
  if (records.some((record) => record.kind === 'pageerror'))
    throw new Error('Chromium reported a JavaScript exception');
  if (autoOrder && !records.some((record) => record.kind === 'console' &&
    record.text.includes(`RTS Bridge selected units=${metrics.actorId}`)))
    throw new Error('The browser did not select the focused Marine');
  if (autoOrder && metrics.actorMoveLatencyMs === undefined)
    throw new Error('The selected Marine did not move after the browser order');
  if (secondOrderDelayMs > 0 && metrics.secondActorMoveLatencyMs === undefined)
    throw new Error('The selected Marine did not move after the second browser order');
  outcome = 'passed';
  console.log(`PASS: browser multiplayer frames in=${metrics.websocketFramesIn} out=${metrics.websocketFramesOut}`);
} catch (error) {
  records.push({ kind: 'failure', text: String(error.stack || error) });
  console.error(`FAIL: ${error.message || error}`);
} finally {
  clearInterval(statusTimer);
  await context?.close();
  await writeFile(path.join(artifacts, 'runtime.json'), JSON.stringify({ outcome, metrics, records }, null, 2) + '\n');
}
if (outcome !== 'passed') process.exitCode = 1;

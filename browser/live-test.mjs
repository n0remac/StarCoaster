// Capture a Chromium OpenRCT2 client against a running native StarCoaster host.
// Licensed RCT2 files must already have been imported at this origin/profile.
import { chromium } from 'playwright-core';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = path.join(root, 'build', 'wasm-live-test');
const profile = process.env.WASM_LIVE_PROFILE || path.join(root, 'build', 'wasm-browser-test', 'chromium-live-profile');
const url = process.env.WASM_LIVE_URL || 'http://127.0.0.1:8091/';
const durationMs = Number(process.env.WASM_LIVE_DURATION_MS || 45000);
const selection = [process.env.WASM_CLICK_X, process.env.WASM_CLICK_Y].map(Number);
const order = [process.env.WASM_ORDER_X, process.env.WASM_ORDER_Y].map(Number);
const haveSelection = process.env.WASM_CLICK_X !== undefined && process.env.WASM_CLICK_Y !== undefined;
const haveOrder = process.env.WASM_ORDER_X !== undefined && process.env.WASM_ORDER_Y !== undefined;
const records = [];
const metrics = { origin: url, startedAt: new Date().toISOString(), websocketFramesIn: 0,
  websocketFramesOut: 0, websocketBytesIn: 0, websocketBytesOut: 0, workers: 0 };
let outcome = 'failed';
let context;

await mkdir(artifacts, { recursive: true });
try {
  context = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    viewport: { width: 1280, height: 800 },
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await context.newPage();
  page.on('console', (message) => {
    const line = message.text();
    records.push({ kind: 'console', text: line });
    if (/index|network|plugin|WORLD_|RTS Bridge|Failed to connect/i.test(line))
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
  await page.waitForTimeout(15000);
  await page.screenshot({ path: path.join(artifacts, 'connected.png') });
  if (haveSelection) {
    await page.mouse.click(...selection);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(artifacts, 'selected.png') });
  }
  if (haveOrder) {
    if (!haveSelection) throw new Error('An order needs WASM_CLICK_X and WASM_CLICK_Y');
    await page.mouse.click(...order, { button: 'right' });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(artifacts, 'ordered.png') });
  }
  for (let elapsed = 0; elapsed < durationMs; elapsed += 30000) {
    await page.waitForTimeout(Math.min(30000, durationMs - elapsed));
    await page.screenshot({ path: path.join(artifacts, `progress-${Math.min(elapsed + 30000, durationMs)}.png`) });
    console.log(`PROGRESS: ${Math.min(elapsed + 30000, durationMs)} ms, ${metrics.websocketFramesIn} inbound frames`);
  }
  await page.screenshot({ path: path.join(artifacts, 'final.png') });
  metrics.elapsedMs = Date.now() - start;
  metrics.heapBytes = await page.evaluate(() => performance.memory?.usedJSHeapSize ?? null);
  metrics.crossOriginIsolated = await page.evaluate(() => crossOriginIsolated);
  if (!metrics.websocketFramesIn || !metrics.websocketFramesOut)
    throw new Error('The browser did not exchange native multiplayer frames over /ws');
  if (records.some((record) => record.kind === 'pageerror'))
    throw new Error('Chromium reported a JavaScript exception');
  outcome = 'passed';
  console.log(`PASS: browser multiplayer frames in=${metrics.websocketFramesIn} out=${metrics.websocketFramesOut}`);
} catch (error) {
  records.push({ kind: 'failure', text: String(error.stack || error) });
  console.error(`FAIL: ${error.message || error}`);
} finally {
  await context?.close();
  await writeFile(path.join(artifacts, 'runtime.json'), JSON.stringify({ outcome, metrics, records }, null, 2) + '\n');
}
if (outcome !== 'passed') process.exitCode = 1;

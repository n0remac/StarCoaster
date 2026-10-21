// Capture a Chromium OpenRCT2 client against a running native StarCoaster host.
// The private Pi origin provisions licensed RCT2 data on first use; other origins
// need an existing local import in this browser profile.
import { chromium } from 'playwright-core';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { execFileSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const perfRun = process.env.WASM_PERF_RUN === '1';
const artifacts = process.env.WASM_PERF_ARTIFACTS || path.join(root, 'build', 'wasm-live-test');
const profile = process.env.WASM_LIVE_PROFILE || path.join(root, 'build', 'wasm-browser-test', 'chromium-live-profile');
const url = process.env.WASM_LIVE_URL || 'http://127.0.0.1:8091/';
const normalHandoff = process.env.WASM_NORMAL_HANDOFF === '1';
const sessionRequestTimeoutMs = 120000;
const durationMs = Number(process.env.WASM_LIVE_DURATION_MS || 45000);
let selection = [process.env.WASM_CLICK_X, process.env.WASM_CLICK_Y].map(Number);
let order = [process.env.WASM_ORDER_X, process.env.WASM_ORDER_Y].map(Number);
let haveSelection = process.env.WASM_CLICK_X !== undefined && process.env.WASM_CLICK_Y !== undefined;
let haveOrder = process.env.WASM_ORDER_X !== undefined && process.env.WASM_ORDER_Y !== undefined;
const cameraProbe = process.env.WASM_LIVE_CAMERA === '1';
const autoOrder = process.env.WASM_AUTO_ORDER === '1';
const cameraSweep = process.env.WASM_CAMERA_SWEEP === '1';
const controlProbe = process.env.WASM_CONTROL_PROBE === '1';
const productionProbe = process.env.WASM_PRODUCTION_PROBE === '1';
const constructionProbe = process.env.WASM_CONSTRUCTION_PROBE === '1';
const demolitionProbe = process.env.WASM_DEMOLITION_PROBE === '1';
const defenseProbe = process.env.WASM_DEFENSE_PROBE === '1';
const defenseConfigure = process.env.WASM_DEFENSE_CONFIGURE === '1';
const defenseMenu = process.env.WASM_DEFENSE_MENU === '1';
const recordVideo = process.env.WASM_LIVE_RECORD === '1';
const recordScreencast = process.env.WASM_LIVE_SCREENCAST === '1';
const secondOrderDelayMs = Number(process.env.WASM_SECOND_ORDER_DELAY_MS || 0);
const captureIntervalMs = Number(process.env.WASM_CAPTURE_INTERVAL_MS || 30000);
const records = [];
const metrics = { origin: perfRun ? 'private-origin' : url, startedAt: new Date().toISOString(), websocketFramesIn: 0,
  websocketFramesOut: 0, websocketBytesIn: 0, websocketBytesOut: 0, workers: 0 };
if (perfRun) {
  let chromiumVersion = null;
  try { chromiumVersion = execFileSync(process.env.CHROMIUM_PATH || '/usr/bin/chromium', ['--version'],
    { encoding: 'utf8', timeout: 5000 }).trim(); } catch (_) {}
  metrics.clientHardware = { platform: process.platform, arch: process.arch,
    cpuCount: os.cpus().length, memoryBytes: os.totalmem(),
    kernel: os.release(), nodeVersion: process.version, chromiumVersion };
}
let outcome = 'failed';
let context;
let screencast;
let statusTimer;
let perfTimer;
let perfEvents;
let perfNetwork;
let perfSystem;
let lastNetwork = { in: 0, out: 0, bytesIn: 0, bytesOut: 0 };
let receivedSizes = [];
let linuxClockTicks = 100;
if (perfRun && process.platform === 'linux') {
  try { linuxClockTicks = Number(execFileSync('getconf', ['CLK_TCK'], { encoding: 'utf8' }).trim()) || 100; }
  catch (_) {}
}
async function chromiumProcessSamples() {
  if (process.platform !== 'linux') return [];
  const pending = [process.pid], seen = new Set(), samples = [];
  while (pending.length) {
    const pid = pending.pop();
    if (seen.has(pid)) continue;
    seen.add(pid);
    try {
      const children = (await readFile(`/proc/${pid}/task/${pid}/children`, 'utf8')).trim();
      if (children) pending.push(...children.split(/\s+/).map(Number));
      const name = (await readFile(`/proc/${pid}/comm`, 'utf8')).trim();
      if (!name.includes('chrom')) continue;
      const stat = (await readFile(`/proc/${pid}/stat`, 'utf8')).split(/\)\s/, 2)[1].split(' ');
      const statm = (await readFile(`/proc/${pid}/statm`, 'utf8')).trim().split(' ');
      samples.push({ type: name, cpu_seconds: (Number(stat[11]) + Number(stat[12])) / linuxClockTicks,
        rss_bytes: Number(statm[1]) * 4096 });
    } catch (_) {}
  }
  return samples;
}
const capture = (page, filename) => perfRun ? Promise.resolve() : page.screenshot({
  path: path.join(artifacts, filename), timeout: 120000,
});

await mkdir(artifacts, { recursive: true });
if (perfRun) {
  perfEvents = createWriteStream(path.join(artifacts, 'browser-events.jsonl'));
  perfNetwork = createWriteStream(path.join(artifacts, 'browser-network.jsonl'));
  perfSystem = createWriteStream(path.join(artifacts, 'browser-system.jsonl'));
}
try {
  context = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    viewport: { width: 1280, height: 800 },
    ...(recordVideo ? { recordVideo: { dir: artifacts, size: { width: 640, height: 400 } } } : {}),
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
  {
    if ([cameraProbe, productionProbe, demolitionProbe, defenseMenu].filter(Boolean).length > 1)
      throw new Error('Choose one live camera, production, or demolition probe');
    const source = cameraProbe || productionProbe || demolitionProbe || defenseMenu
      ? await readFile(path.join(root, defenseMenu ? 'browser/defense-menu-probe.js'
      : productionProbe || demolitionProbe ? 'scripts/native-production-hud-capture.js'
      : 'browser/live-camera.js'), 'utf8') : '';
    const cameraSource = defenseMenu ? source : defenseProbe
      ? 'var STARCOASTER_CAMERA_NO_MOVE = true;\n'
        + source.replaceAll('terran_marine', 'zerg_zergling')
      : demolitionProbe
      ? 'var STARCOASTER_HUD_INITIAL_FOCUS = 6;\nvar STARCOASTER_HUD_DRIVER = true;\n' + source
      : productionProbe ? 'var STARCOASTER_HUD_INITIAL_FOCUS = 2;\n'
      + (constructionProbe ? 'var STARCOASTER_HUD_CONSTRUCTION_PROBE = true;\n' : '') + source
      : process.env.WASM_LIVE_NO_MOVE === '1'
        ? 'var STARCOASTER_CAMERA_NO_MOVE = true;\n' + source
      : cameraSweep ? 'var STARCOASTER_CAMERA_SWEEP = true;\n' + source
      : controlProbe ? 'var STARCOASTER_CAMERA_ALL_ACTORS = true;\n' + source : source;
    const perfCameraSource = perfRun && cameraProbe
      ? 'var STARCOASTER_PERF_CAMERA = ' + JSON.stringify(process.env.WASM_PERF_CAMERA || 'visible') + ';\n'
        + 'var STARCOASTER_PERF_WORKLOAD = ' + JSON.stringify(process.env.WASM_PERF_WORKLOAD || 'idle') + ';\n'
        + 'var STARCOASTER_PERF_COMMAND_DELAY_MS = ' + JSON.stringify(
          Number(process.env.WASM_PERF_WARMUP_MS || 15000) + 10000) + ';\n'
        + cameraSource : cameraSource;
    const defenseSource = defenseConfigure
      ? 'var UNIVERSAL_DEFENSE_ANCHOR = ' + JSON.stringify(
        (process.env.WASM_DEFENSE_ANCHOR || '4,4').split(',').map(Number)) + ';\n'
        + (process.env.WASM_DEFENSE_MANUAL === '1' ? 'var UNIVERSAL_DEFENSE_VERIFY_MANUAL = true;\n' : '')
        + (process.env.WASM_DEFENSE_BUILD === '1' ? 'var UNIVERSAL_DEFENSE_VERIFY_BUILD = true;\n' : '')
        + (process.env.WASM_DEFENSE_NO_WAVE === '1' ? 'var UNIVERSAL_DEFENSE_VERIFY_NO_WAVE = true;\n' : '')
        + await readFile(path.join(root, 'tests/universal-defense-probe.js'), 'utf8') : '';
    await page.addInitScript(({ cameraSource, defenseSource, perfRun, perfBaseline, suppressPaint }) => {
      if (perfRun) {
        window.__starPerf = { longTasks: 0, longTaskMs: 0, maxLongTaskMs: 0 };
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            window.__starPerf.longTasks++;
            window.__starPerf.longTaskMs += entry.duration;
            window.__starPerf.maxLongTaskMs = Math.max(window.__starPerf.maxLongTaskMs, entry.duration);
          }
        }).observe({ type: 'longtask', buffered: true });
      }
      Object.defineProperty(window, 'Module', {
        configurable: true,
        set(module) {
          Object.defineProperty(window, 'Module', { value: module, configurable: true });
          if (perfRun) module.ENV = Object.assign({}, module.ENV, {
            STARCOASTER_PERF: perfBaseline ? '0' : '1',
            STARCOASTER_SUPPRESS_PAINT: suppressPaint ? '1' : '0',
          });
          const original = module.callMain.bind(module);
          module.callMain = (args) => {
            module.FS.mkdirTree('/persistent/plugin');
            if (cameraSource) module.FS.writeFile('/persistent/plugin/wasm-live-camera.js', cameraSource);
            else {
              try { module.FS.unlink('/persistent/plugin/wasm-live-camera.js'); } catch (_) {}
            }
            if (defenseSource) module.FS.writeFile('/persistent/plugin/wasm-defense-probe.js', defenseSource);
            else {
              try { module.FS.unlink('/persistent/plugin/wasm-defense-probe.js'); } catch (_) {}
            }
            original(args);
          };
        },
      });
    }, { cameraSource: perfCameraSource, defenseSource, perfRun,
      perfBaseline: process.env.WASM_PERF_BASELINE === '1',
      suppressPaint: process.env.WASM_PERF_SUPPRESS_PAINT === '1' });
  }
  let resolveCamera;
  const cameraReady = new Promise((resolve) => { resolveCamera = resolve; });
  let resolveEarlyDisconnect;
  const earlyDisconnect = new Promise((resolve) => { resolveEarlyDisconnect = resolve; });
  let snapshotReady = false;
  let resolveActorScreen;
  const actorScreenReady = new Promise((resolve) => { resolveActorScreen = resolve; });
  page.on('console', (message) => {
    const line = message.text();
    if (perfRun && line.includes('STARCOASTER_PERF ')) {
      try {
        const match = /STARCOASTER_PERF (\{.*\})/.exec(line);
        const event = JSON.parse(match[1]);
        perfEvents.write(JSON.stringify(Object.assign({ role: 'browser-client', wall_ms: Date.now() }, event)) + '\n');
      } catch (_) {}
    } else if (!perfRun || records.length < 10000) {
      records.push({ kind: 'console', text: line, at: Date.now() });
    }
    if (line.includes('WASM_CAMERA_READY') || line.includes('NATIVE_HUD_CAPTURE_READY')) {
      snapshotReady = true;
      resolveCamera();
    }
    const screen = /WASM_ACTOR_SCREEN id=([^ ]+) x=([\d.]+) y=([\d.]+)/.exec(line);
    if (screen) resolveActorScreen({ id: screen[1], x: Number(screen[2]), y: Number(screen[3]) });
    if (line.includes('WASM_ACTOR_MOVED') && metrics.orderSentAt && metrics.actorMoveLatencyMs === undefined)
      metrics.actorMoveLatencyMs = Date.now() - metrics.orderSentAt;
    if (line.includes('WASM_ACTOR_MOVED') && metrics.secondOrderSentAt &&
      metrics.secondActorMoveLatencyMs === undefined)
      metrics.secondActorMoveLatencyMs = Date.now() - metrics.secondOrderSentAt;
    if ((!perfRun || !line.includes('STARCOASTER_PERF ')) && !line.includes('Paint.Entity.cpp')
      && /index|network|plugin|WORLD_|RTS Bridge|UNIVERSAL_DEFENSE|WASM_CAMERA|WASM_ACTOR|NATIVE_HUD|Failed to connect/i.test(line))
      console.log(`CLIENT: ${line}`);
  });
  page.on('pageerror', (error) => records.push({ kind: 'pageerror', text: error.message }));
  page.on('worker', () => metrics.workers++);
  page.on('websocket', (socket) => {
    records.push({ kind: 'websocket', url: perfRun ? '/ws' : socket.url() });
    console.log(`WEBSOCKET: ${perfRun ? '/ws' : socket.url()}`);
    socket.on('framereceived', (frame) => {
      metrics.websocketFramesIn++;
      const bytes = Buffer.byteLength(frame.payload);
      metrics.websocketBytesIn += bytes;
      if (perfRun && receivedSizes.length < 4096) receivedSizes.push(bytes);
    });
    socket.on('framesent', (frame) => {
      metrics.websocketFramesOut++;
      metrics.websocketBytesOut += Buffer.byteLength(frame.payload);
    });
    socket.on('socketerror', (error) => {
      records.push({ kind: 'websocketerror', text: String(error) });
      if (!snapshotReady) resolveEarlyDisconnect(`Multiplayer WebSocket error before native snapshot: ${error}`);
    });
    socket.on('close', () => {
      records.push({ kind: 'websocketclose', url: perfRun ? '/ws' : socket.url() });
      if (!snapshotReady) resolveEarlyDisconnect('Multiplayer WebSocket closed before native snapshot');
    });
  });
  if (perfRun) {
    const cdp = await context.newCDPSession(page);
    await cdp.send('Performance.enable');
    perfTimer = setInterval(async () => {
      const now = Date.now();
      const current = { in: metrics.websocketFramesIn, out: metrics.websocketFramesOut,
        bytesIn: metrics.websocketBytesIn, bytesOut: metrics.websocketBytesOut };
      perfNetwork.write(JSON.stringify({ source: 'browser', stage: 'websocket_second', wall_ms: now,
        messages_in: current.in - lastNetwork.in, messages_out: current.out - lastNetwork.out,
        bytes_in: current.bytesIn - lastNetwork.bytesIn, bytes_out: current.bytesOut - lastNetwork.bytesOut,
        max_message_bytes: receivedSizes.length ? Math.max(...receivedSizes) : 0,
        connections: records.filter((r) => r.kind === 'websocket').length,
        closes: records.filter((r) => r.kind === 'websocketclose').length }) + '\n');
      lastNetwork = current; receivedSizes = [];
      try {
        const [{ metrics: entries }, browser, processInfo] = await Promise.all([
          cdp.send('Performance.getMetrics'), page.evaluate(() => ({
            heap_bytes: performance.memory?.usedJSHeapSize ?? null,
            long_tasks: window.__starPerf?.longTasks ?? null,
            long_task_ms: window.__starPerf?.longTaskMs ?? null,
            max_long_task_ms: window.__starPerf?.maxLongTaskMs ?? null,
          })), cdp.send('SystemInfo.getProcessInfo').catch(() => ({ processInfo: [] })),
        ]);
        const values = Object.fromEntries(entries.map((m) => [m.name, m.value]));
        let chromiumProcesses = await Promise.all(processInfo.processInfo.map(async (process) => {
          let rssBytes = null;
          try {
            if (process.platform === undefined) {
              const statm = (await readFile(`/proc/${process.id}/statm`, 'utf8')).trim().split(' ');
              rssBytes = Number(statm[1]) * 4096;
            }
          } catch (_) {}
          return { type: process.type, cpu_seconds: process.cpuTime, rss_bytes: rssBytes };
        }));
        if (!chromiumProcesses.length) chromiumProcesses = await chromiumProcessSamples();
        perfSystem.write(JSON.stringify({ source: 'chromium', wall_ms: now,
          task_cpu_seconds: values.TaskDuration ?? null, js_heap_bytes: browser.heap_bytes,
          long_tasks: browser.long_tasks, long_task_ms: browser.long_task_ms,
          max_long_task_ms: browser.max_long_task_ms, processes: chromiumProcesses }) + '\n');
      } catch (_) {}
    }, 1000);
  }
  const start = Date.now();
  const testUrl = new URL(url);
  if (!normalHandoff) {
    testUrl.searchParams.set('starcoaster-test-join', '1');
    if (process.env.WASM_TEST_PORT) testUrl.searchParams.set('starcoaster-test-port', process.env.WASM_TEST_PORT);
  }
  if (perfRun) {
    testUrl.searchParams.set('starcoaster-performance', '1');
    if (process.env.WASM_PERF_BASELINE === '1')
      testUrl.searchParams.set('starcoaster-performance-baseline', '1');
    if (process.env.WASM_PERF_SUPPRESS_PAINT === '1')
      testUrl.searchParams.set('starcoaster-suppress-paint', '1');
  }
  await page.goto(testUrl.href, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() =>
    document.getElementById('canvas')?.style.display === 'block' ||
    document.getElementById('status')?.classList.contains('error'),
  null, { timeout: Number(process.env.WASM_LIVE_BOOT_TIMEOUT_MS || 180000) });
  if (await page.locator('#status.error').count())
    throw new Error(await page.locator('#status.error #message').textContent());
  if (normalHandoff) {
    const sessionURL = new URL('/private/park-session', url).href;
    const before = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
    if (before.phase !== 'idle' && !(process.env.WASM_HANDOFF_ALLOW_READY === '1' && before.phase === 'ready'))
      throw new Error(`Handoff test expected an idle host: ${before.phase}`);
    console.log('HANDOFF: waiting for OpenRCT2 title screen');
    let indexReady = false;
    for (let elapsed = 0; elapsed < 300000; elapsed += 1000) {
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('Finished building object index'))) {
        indexReady = true;
        break;
      }
      await page.waitForTimeout(1000);
    }
    if (!indexReady) throw new Error('OpenRCT2 did not finish its object index');
    let mainMenu = false;
    for (let elapsed = 0; elapsed < 300000; elapsed += 5000) {
      await page.waitForTimeout(5000);
      const screenshot = await capture(page, 'handoff-main-menu.png');
      if (screenshot.length > 100000) { mainMenu = true; break; }
    }
    if (!mainMenu) throw new Error('OpenRCT2 did not render its main menu');
    console.log('HANDOFF: clicking New Game');
    await page.mouse.click(514, 688);
    await page.waitForTimeout(5000);
    await capture(page, 'handoff-scenario-browser.png');
    const [initialLabel, initialRow] = (process.env.WASM_HANDOFF_INITIAL || 'Bumbly Bazaar:340').split(':');
    console.log(`HANDOFF: selecting ${initialLabel}`);
    await page.mouse.click(555, Number(initialRow));
    let ready = false;
    for (let elapsed = 0; elapsed < 240000; elapsed += 1000) {
      const state = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
      if (state.phase === 'ready' && state.generation !== before.generation) {
        metrics.handoffGeneration = state.generation;
        ready = true;
        break;
      }
      if (state.error && (state.phase === 'idle' || state.phase === 'failed'))
        throw new Error(`Authoritative handoff failed: ${state.error}`);
      await page.waitForTimeout(1000);
    }
    if (!ready) throw new Error('Normal scenario selection did not establish a new generation');
    console.log(`HANDOFF: ready generation=${metrics.handoffGeneration}`);
    if (process.env.WASM_HANDOFF_MENU_CAPTURE === '1') {
      for (let elapsed = 0; elapsed < 180000; elapsed += 1000) {
        if (records.some((record) => record.kind === 'console' &&
          record.text.includes('WORLD_SCENARIO_STATUS scenario='))) break;
        await page.waitForTimeout(1000);
      }
      if (!records.some((record) => record.kind === 'console' &&
        record.text.includes('WORLD_SCENARIO_STATUS scenario=')))
        throw new Error('Client did not receive authoritative scenario status');
      await page.mouse.click(15, 12);
      await capture(page, 'handoff-file-menu.png');
    }
  }
  // OpenRCT2 scrolls its viewport while the pointer rests on a screen edge.
  // Keep the camera fixed through actor selection and mixed-client delays.
  await page.mouse.move(640, 400);
  metrics.canvasMs = Date.now() - start;
  if (cameraProbe || productionProbe || demolitionProbe) {
    let timeout;
    try {
      await Promise.race([cameraReady, earlyDisconnect.then((message) => { throw new Error(message); }),
        new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error('The live probe did not observe a native snapshot')), 420000);
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
  if (recordScreencast) {
    const frames = path.join(artifacts, 'screencast');
    await rm(frames, { recursive: true, force: true });
    await mkdir(frames, { recursive: true });
    screencast = await context.newCDPSession(page);
    let frameNumber = 0;
    screencast.on('Page.screencastFrame', async ({ data, sessionId }) => {
      try {
        if (frameNumber < 300) {
          frameNumber++;
          await writeFile(path.join(frames, `frame-${String(frameNumber).padStart(4, '0')}.jpg`),
            Buffer.from(data, 'base64'));
        }
      } finally {
        await screencast.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
      }
    });
    await screencast.send('Page.startScreencast', {
      format: 'jpeg', quality: 70, maxWidth: 640, maxHeight: 400, everyNthFrame: 30,
    });
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
  if (defenseMenu) {
    for (let elapsed = 0; elapsed < 90000; elapsed += 1000) {
      if (records.some((record) => record.kind === 'console'
        && record.text.includes('WORLD_SCENARIO_STATUS scenario='))) break;
      await page.waitForTimeout(1000);
    }
    if (!records.some((record) => record.kind === 'console'
      && record.text.includes('WORLD_SCENARIO_STATUS scenario=')))
      throw new Error('The browser did not receive authoritative defense status');
    await page.mouse.click(1105, 12);
    let construction;
    for (let elapsed = 0; elapsed < 15000; elapsed += 1000) {
      const line = records.find((record) => record.kind === 'console'
        && record.text.includes('DEFENSE_CONSTRUCTION_WINDOW x='))?.text;
      const match = /DEFENSE_CONSTRUCTION_WINDOW x=(\d+) y=(\d+) width=(\d+) height=(\d+)/.exec(line || '');
      if (match) { construction = { x: Number(match[1]), y: Number(match[2]),
        width: Number(match[3]), height: Number(match[4]) }; break; }
      await page.waitForTimeout(1000);
    }
    if (!construction) throw new Error('The SC toolbar did not open Construction');
    await capture(page, 'starcraft-construction.png');
    await page.mouse.click(construction.x + 120, construction.y + construction.height - 30);
    for (let elapsed = 0; elapsed < 15000; elapsed += 1000) {
      if (records.some((record) => record.kind === 'console'
        && record.text.includes('DEFENSE_WINDOW x='))) break;
      await page.waitForTimeout(1000);
    }
    if (!records.some((record) => record.kind === 'console'
      && record.text.includes('DEFENSE_WINDOW x=')))
      throw new Error('Construction did not open StarCraft Defense');
    await capture(page, 'starcraft-defense.png');
  }
  if (controlProbe) {
    if (!cameraProbe) throw new Error('WASM_CONTROL_PROBE requires WASM_LIVE_CAMERA=1');
    let actors;
    for (let elapsed = 0; elapsed < 60000; elapsed += 1000) {
      const line = records.find((record) => record.kind === 'console' &&
        record.text.includes('WASM_ACTOR_SCREENS '))?.text;
      if (line) {
        const start = line.indexOf('[', line.indexOf('WASM_ACTOR_SCREENS '));
        actors = JSON.parse(line.slice(start, line.lastIndexOf(']') + 1));
        break;
      }
      await page.waitForTimeout(1000);
    }
    if (!actors || actors.length < 2) throw new Error('The browser did not render two controllable Marines');
    metrics.controlActors = actors;
    const left = Math.floor(Math.min(...actors.map((actor) => actor.x)) - 20);
    const top = Math.floor(Math.min(...actors.map((actor) => actor.y)) - 32);
    const right = Math.ceil(Math.max(...actors.map((actor) => actor.x)) + 20);
    const bottom = Math.ceil(Math.max(...actors.map((actor) => actor.y)) + 14);
    const selectionCount = () => {
      const line = records.filter((record) => record.kind === 'console' &&
        record.text.includes('RTS Bridge selected units=')).at(-1)?.text || '';
      return line.split('selected units=')[1]?.split(',').filter(Boolean).length || 0;
    };
    await page.mouse.move(left, top);
    await page.mouse.down();
    await page.mouse.move(right, bottom, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(1000);
    metrics.rectangleSelected = selectionCount();
    if (metrics.rectangleSelected < 2) throw new Error('Browser rectangle selection missed the Marines');
    await capture(page, 'rectangle-selected.png');
    const isolated = actors.reduce((best, actor) => {
      const nearest = Math.min(...actors.filter((other) => other !== actor).map((other) =>
        Math.hypot(other.x - actor.x, other.y - actor.y)));
      return !best || nearest > best.nearest ? { actor, nearest } : best;
    }, null).actor;
    await page.keyboard.down('Shift');
    await page.mouse.click(isolated.x, isolated.y - 8);
    await page.keyboard.up('Shift');
    await page.waitForTimeout(700);
    metrics.shiftRemoved = selectionCount();
    if (metrics.shiftRemoved !== metrics.rectangleSelected - 1)
      throw new Error('Shift-click did not remove one Marine from the selection');
    await page.keyboard.down('Shift');
    await page.mouse.click(isolated.x, isolated.y - 8);
    await page.keyboard.up('Shift');
    await page.waitForTimeout(700);
    if (selectionCount() !== metrics.rectangleSelected)
      throw new Error('Shift-click did not restore the Marine selection');
    const beforeAlt = records.length;
    await page.keyboard.down('Alt');
    await page.mouse.click(isolated.x, isolated.y - 8);
    await page.keyboard.up('Alt');
    await page.waitForTimeout(700);
    if (records.slice(beforeAlt).some((record) => record.kind === 'console' &&
      record.text.includes('RTS Bridge selected units=')))
      throw new Error('Alt-click changed Marine selection instead of passing to the park');
    const waitAccepted = async (after, label) => {
      for (let elapsed = 0; elapsed < 30000; elapsed += 1000) {
        if (records.slice(after).some((record) => record.kind === 'console' &&
          /RTS Bridge Marine command request=.* accepted=true/.test(record.text))) return;
        await page.waitForTimeout(1000);
      }
      throw new Error(`Browser ${label} order received no accepted result`);
    };
    const target = [Math.min(1100, isolated.x + 30), Math.min(700, isolated.y + 85)];
    let after = records.length;
    await page.keyboard.press('a');
    await page.mouse.click(...target, { button: 'right' });
    await waitAccepted(after, 'attack-move');
    metrics.attackMoveAccepted = true;
    after = records.length;
    await page.keyboard.press('s');
    await waitAccepted(after, 'stop');
    metrics.stopAccepted = true;
    after = records.length;
    await page.keyboard.press('h');
    await waitAccepted(after, 'hold');
    metrics.holdAccepted = true;
    await capture(page, 'controls-complete.png');
  }
  if (demolitionProbe) {
    for (const point of [[640, 400], [630, 390], [650, 410]]) {
      await page.mouse.click(...point);
      await page.waitForTimeout(1200);
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('NATIVE_HUD_INSPECTOR_OPEN building=Armory'))) break;
    }
    if (!records.some((record) => record.kind === 'console' &&
      record.text.includes('NATIVE_HUD_INSPECTOR_OPEN building=Armory')))
      throw new Error('The browser did not open the Armory inspector');
    await capture(page, 'armory-inspector.png');
    await page.keyboard.press('Control+Shift+D');
    for (let elapsed = 0; elapsed < 60000; elapsed += 1000) {
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('NATIVE_HUD_DEMOLISH accepted=true'))) break;
      await page.waitForTimeout(1000);
    }
    if (!records.some((record) => record.kind === 'console' &&
      record.text.includes('NATIVE_HUD_DEMOLISH accepted=true')))
      throw new Error('The browser Armory demolition action was rejected');
    metrics.demolitionAccepted = true;
    await page.waitForTimeout(3000);
    await capture(page, 'armory-demolished.png');
  }
  if (productionProbe) {
    for (const point of [[640, 400], [630, 390], [650, 410]]) {
      await page.mouse.click(...point);
      console.log(`BUILDING_CLICK: ${JSON.stringify(point)}`);
      await page.waitForTimeout(1500);
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('NATIVE_HUD_INSPECTOR_OPEN building=Barracks'))) break;
    }
    if (!records.some((record) => record.kind === 'console' &&
      record.text.includes('NATIVE_HUD_INSPECTOR_OPEN building=Barracks')))
      throw new Error('The browser did not open the Barracks inspector');
    for (let elapsed = 0; elapsed < 120000; elapsed += 1000) {
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('NATIVE_HUD_INSPECTOR_READY building=Barracks'))) break;
      await page.waitForTimeout(1000);
    }
    if (!records.some((record) => record.kind === 'console' &&
      record.text.includes('NATIVE_HUD_INSPECTOR_READY building=Barracks')))
      throw new Error('The browser Barracks did not receive native production state');
    await capture(page, 'barracks-inspector.png');
    await page.mouse.click(1147, 80);
    console.log('BUILDING_TRAIN: Marine');
    let accepted = false;
    for (let elapsed = 0; elapsed < 90000; elapsed += 1000) {
      await page.waitForTimeout(1000);
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('WORLD_TRAIN_RESULT id=scenario:hud-barracks accepted=true'))) {
        accepted = true;
        break;
      }
    }
    if (!accepted) throw new Error('The browser Barracks did not receive an accepted native training result');
    metrics.productionAccepted = true;
    await capture(page, 'barracks-training.png');
    if (constructionProbe) {
      await page.mouse.click(1272, 37);
      await page.mouse.click(1076, 12);
      let menu;
      for (let elapsed = 0; elapsed < 15000; elapsed += 1000) {
        const line = records.find((record) => record.kind === 'console' &&
          record.text.includes('NATIVE_HUD_CONSTRUCTION_WINDOW x='))?.text;
        const match = /NATIVE_HUD_CONSTRUCTION_WINDOW x=(\d+) y=(\d+) width=(\d+)/.exec(line || '');
        if (match) { menu = { x: Number(match[1]), y: Number(match[2]) }; break; }
        await page.waitForTimeout(1000);
      }
      if (!menu) throw new Error('The StarCraft construction toolbar did not open');
      await capture(page, 'construction-menu.png');
      await page.mouse.click(menu.x + 120, menu.y + 48);
      let site;
      for (const point of [[760, 550], [900, 550], [750, 650], [500, 500]]) {
        const movedAt = Date.now();
        await page.mouse.move(...point);
        await page.waitForTimeout(1800);
        if (records.some((record) => record.kind === 'console' && record.at >= movedAt &&
          record.text.includes('NATIVE_HUD_CONSTRUCTION_STATUS text=Valid site - click to build'))) {
          site = point;
          break;
        }
      }
      if (!site) throw new Error('No candidate Barracks site passed native park clearance');
      metrics.constructionSite = site;
      await capture(page, 'construction-preview.png');
      await page.mouse.click(...site);
      for (let elapsed = 0; elapsed < 60000; elapsed += 1000) {
        if (records.some((record) => record.kind === 'console' &&
          record.text.includes('NATIVE_HUD_CONSTRUCTION_STATUS text=Terran Barracks constructed'))) break;
        await page.waitForTimeout(1000);
      }
      if (!records.some((record) => record.kind === 'console' &&
        record.text.includes('NATIVE_HUD_CONSTRUCTION_STATUS text=Terran Barracks constructed')))
        throw new Error('The browser Barracks placement was not accepted');
      metrics.constructionAccepted = true;
      await capture(page, 'construction-placed.png');
    }
  }
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
  if (process.env.WASM_HANDOFF_REQUIRE_WAVE === '1') {
    for (const [label, pattern, timeoutMs] of [
      ['authoritative wave acceptance', 'WORLD_WAVE_RESULT accepted=true', 120000],
      ['native Zerg actor', 'UNIVERSAL_DEFENSE_ZERG id=', 120000],
      ['authoritative combat damage', 'UNIVERSAL_DEFENSE_COMBAT id=', 180000],
    ]) {
      let observed = false;
      for (let elapsed = 0; elapsed < timeoutMs; elapsed += 1000) {
        if (records.some((record) => record.kind === 'console' && record.text.includes(pattern))) {
          observed = true;
          break;
        }
        await page.waitForTimeout(1000);
      }
      if (!observed) throw new Error(`The stock scenario did not report ${label}`);
      console.log(`HANDOFF: ${label} verified`);
    }
    await capture(page, 'handoff-first-combat.png');
  }
  if (process.env.WASM_HANDOFF_SWITCH === '1') {
    const sessionURL = new URL('/private/park-session', url).href;
    let previous = (await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json()).generation;
    let previousStatus = records.filter((record) => record.kind === 'console' &&
      record.text.includes('WORLD_SCENARIO_STATUS scenario=')).at(-1)?.text || '';
    const switchTargets = process.env.WASM_HANDOFF_SWITCH_TARGETS
      ? process.env.WASM_HANDOFF_SWITCH_TARGETS.split(',').map((target) => {
        const [label, row] = target.split(':');
        return [label, Number(row)];
      })
      : [['Electric Fields', 245], ['Bumbly Bazaar', 340]];
    for (const [label, row] of switchTargets) {
      await page.mouse.click(15, 12);
      await page.mouse.click(40, 36);
      await page.waitForTimeout(1000);
      await capture(page, `handoff-${label.replaceAll(' ', '-').toLowerCase()}-prompt.png`);
      await page.mouse.click(640, 408);
      await page.waitForTimeout(5000);
      await capture(page, `handoff-${label.replaceAll(' ', '-').toLowerCase()}-browser.png`);
      console.log(`HANDOFF: selecting ${label} from in-game New Game`);
      await page.mouse.click(555, row);
      let next;
      for (let elapsed = 0; elapsed < 240000; elapsed += 1000) {
        const state = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
        if (state.phase === 'ready' && state.generation !== previous) {
          next = state;
          break;
        }
        if (state.error && state.phase === 'ready' && state.generation === previous)
          throw new Error(`Replacement ${label} failed: ${state.error}`);
        await page.waitForTimeout(1000);
      }
      if (!next) throw new Error(`Replacement ${label} did not establish a new generation`);
      if (next.current.toLowerCase() !== `${label}.sc6`.toLowerCase())
        throw new Error(`Selected ${label}, supervisor activated ${next.current}`);
      let synchronized = false;
      for (let elapsed = 0; elapsed < 180000; elapsed += 1000) {
        const status = records.filter((record) => record.kind === 'console' &&
          record.text.includes('WORLD_SCENARIO_STATUS scenario=')).at(-1)?.text || '';
        if (status && status !== previousStatus) {
          previousStatus = status;
          synchronized = true;
          break;
        }
        await page.waitForTimeout(1000);
      }
      if (!synchronized) throw new Error(`${label} did not synchronize to the browser client`);
      if (cameraProbe) {
        let actorsReset = false;
        for (let elapsed = 0; elapsed < 30000; elapsed += 1000) {
          const sessions = records.filter((record) => record.kind === 'console' &&
            record.text.includes('WASM_CAMERA_SESSION session='));
          const latest = sessions.at(-1)?.text || '';
          if (sessions.length >= (metrics.switchGenerations?.length || 0) + 2 &&
            !latest.includes(`ids=${metrics.actorId}`)) {
            actorsReset = true;
            break;
          }
          await page.waitForTimeout(1000);
        }
        if (!actorsReset) throw new Error(`${label} retained an actor from the prior session`);
      }
      if (process.env.WASM_HANDOFF_REQUIRE_GAMEPLAY === '1') {
        const expected = (metrics.switchGenerations?.length || 0) + 2;
        let produced = false;
        for (let elapsed = 0; elapsed < 240000; elapsed += 1000) {
          const actors = records.filter((record) => record.kind === 'console' &&
            record.text.includes('WASM_CAMERA_READY session='));
          if (actors.length >= expected) {
            produced = true;
            break;
          }
          await page.waitForTimeout(1000);
        }
        if (!produced) throw new Error(`${label} did not produce a new OpenBW Marine`);
      }
      previous = next.generation;
      metrics.switchGenerations = [...(metrics.switchGenerations || []), previous];
      await capture(page, `handoff-${label.replaceAll(' ', '-').toLowerCase()}-joined.png`);
      console.log(`HANDOFF: switched ${label} generation=${previous}`);
    }
  }
  if (process.env.WASM_HANDOFF_LOAD_SAVE_FILE) {
    const sessionURL = new URL('/private/park-session', url).href;
    const before = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
    if (before.phase !== 'ready') throw new Error('Load Game requires a ready authoritative session');
    let joined = false;
    for (let elapsed = 0; elapsed < 180000; elapsed += 1000) {
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('WORLD_SCENARIO_STATUS scenario='))) { joined = true; break; }
      await page.waitForTimeout(1000);
    }
    if (!joined) throw new Error('Client did not enter the authoritative game before Load Game');
    const previousStatus = records.filter((record) => record.kind === 'console' &&
      record.text.includes('WORLD_SCENARIO_STATUS scenario=')).at(-1)?.text;
    await page.evaluate(() => { window.showOpenFilePicker = undefined; });
    if (process.env.WASM_HANDOFF_MENU_CAPTURE !== '1') await page.mouse.click(15, 12);
    const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 30000 });
    await page.mouse.click(40, 47);
    const immediateChooser = await Promise.race([
      fileChooserPromise,
      page.waitForTimeout(1500).then(() => null),
    ]);
    if (!immediateChooser) {
      await capture(page, 'handoff-load-save-prompt.png');
      await page.mouse.click(640, 408); // Don't Save in OpenRCT2's ordinary prompt.
    }
    const chooser = immediateChooser || await fileChooserPromise;
    await chooser.setFiles(process.env.WASM_HANDOFF_LOAD_SAVE_FILE);
    console.log('HANDOFF: selected user save through Load Game');
    let loaded;
    for (let elapsed = 0; elapsed < 240000; elapsed += 1000) {
      const state = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
      if (state.phase === 'ready' && state.generation !== before.generation) {
        loaded = state;
        break;
      }
      if (state.error && state.phase === 'ready' && state.generation === before.generation)
        throw new Error(`User save failed: ${state.error}`);
      await page.waitForTimeout(1000);
    }
    if (!loaded || !loaded.current.endsWith('.park'))
      throw new Error('Load Game did not establish a new authoritative save generation');
    let synchronized = false;
    for (let elapsed = 0; elapsed < 180000; elapsed += 1000) {
      const currentStatus = records.filter((record) => record.kind === 'console' &&
        record.text.includes('WORLD_SCENARIO_STATUS scenario=')).at(-1)?.text;
      if (currentStatus && currentStatus !== previousStatus) { synchronized = true; break; }
      await page.waitForTimeout(1000);
    }
    if (!synchronized) throw new Error('Load Game did not synchronize the new save to the browser');
    metrics.loadedSaveGeneration = loaded.generation;
    console.log(`HANDOFF: user save ready generation=${loaded.generation}`);
    await capture(page, 'handoff-user-save-joined.png');
  }
  if (process.env.WASM_HANDOFF_RETURN_TITLE === '1') {
    const sessionURL = new URL('/private/park-session', url).href;
    const before = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
    if (before.phase !== 'ready') throw new Error('Return to title requires a ready authoritative session');
    await page.mouse.click(15, 12);
    await page.mouse.click(40, 191);
    await page.waitForTimeout(1000);
    await capture(page, 'handoff-return-title-prompt.png');
    await page.mouse.click(640, 408); // Don't Save.
    let idle = false;
    for (let elapsed = 0; elapsed < 30000; elapsed += 500) {
      const state = await (await context.request.get(sessionURL, { timeout: sessionRequestTimeoutMs })).json();
      if (state.phase === 'idle' && !state.generation) { idle = true; break; }
      await page.waitForTimeout(500);
    }
    if (!idle) throw new Error('Return to title did not clean up the authoritative session');
    console.log('HANDOFF: returned to title and supervisor is idle');
    await capture(page, 'handoff-returned-to-title.png');
  }
  if (perfRun) await page.waitForTimeout(Number(process.env.WASM_PERF_WARMUP_MS || 0));
  metrics.measureStartBrowserMonoMs = await page.evaluate(() => performance.timeOrigin + performance.now());
  metrics.measureStartWallMs = Date.now();
  for (let elapsed = 0; elapsed < durationMs; elapsed += captureIntervalMs) {
    const step = Math.min(captureIntervalMs, durationMs - elapsed);
    await page.waitForTimeout(step);
    await capture(page, `progress-${elapsed + step}.png`);
    console.log(`PROGRESS: ${elapsed + step} ms, ${metrics.websocketFramesIn} inbound frames`);
  }
  metrics.measureEndWallMs = Date.now();
  metrics.measureEndBrowserMonoMs = metrics.measureStartBrowserMonoMs + durationMs;
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
  clearInterval(perfTimer);
  if (screencast) await screencast.send('Page.stopScreencast').catch(() => {});
  await context?.close();
  await writeFile(path.join(artifacts, 'runtime.json'), JSON.stringify({ outcome, metrics, records }, null, 2) + '\n');
  for (const stream of [perfEvents, perfNetwork, perfSystem])
    if (stream) await new Promise((resolve) => stream.end(resolve));
}
if (outcome !== 'passed') process.exitCode = 1;

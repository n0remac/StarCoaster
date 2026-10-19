// Capture a Chromium OpenRCT2 client against a running native StarCoaster host.
// The private Pi origin provisions licensed RCT2 data on first use; other origins
// need an existing local import in this browser profile.
import { chromium } from 'playwright-core';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
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
const controlProbe = process.env.WASM_CONTROL_PROBE === '1';
const productionProbe = process.env.WASM_PRODUCTION_PROBE === '1';
const constructionProbe = process.env.WASM_CONSTRUCTION_PROBE === '1';
const demolitionProbe = process.env.WASM_DEMOLITION_PROBE === '1';
const defenseProbe = process.env.WASM_DEFENSE_PROBE === '1';
const defenseConfigure = process.env.WASM_DEFENSE_CONFIGURE === '1';
const recordVideo = process.env.WASM_LIVE_RECORD === '1';
const recordScreencast = process.env.WASM_LIVE_SCREENCAST === '1';
const secondOrderDelayMs = Number(process.env.WASM_SECOND_ORDER_DELAY_MS || 0);
const captureIntervalMs = Number(process.env.WASM_CAPTURE_INTERVAL_MS || 30000);
const records = [];
const metrics = { origin: url, startedAt: new Date().toISOString(), websocketFramesIn: 0,
  websocketFramesOut: 0, websocketBytesIn: 0, websocketBytesOut: 0, workers: 0 };
let outcome = 'failed';
let context;
let screencast;
let statusTimer;
const capture = (page, filename) => page.screenshot({
  path: path.join(artifacts, filename), timeout: 120000,
});

await mkdir(artifacts, { recursive: true });
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
  if (cameraProbe || productionProbe || demolitionProbe) {
    if ([cameraProbe, productionProbe, demolitionProbe].filter(Boolean).length !== 1)
      throw new Error('Choose one live camera, production, or demolition probe');
    const source = await readFile(path.join(root, productionProbe || demolitionProbe
      ? 'scripts/native-production-hud-capture.js' : 'browser/live-camera.js'), 'utf8');
    const cameraSource = defenseProbe
      ? 'var STARCOASTER_CAMERA_NO_MOVE = true;\n'
        + source.replaceAll('terran_marine', 'zerg_zergling')
      : demolitionProbe
      ? 'var STARCOASTER_HUD_INITIAL_FOCUS = 6;\nvar STARCOASTER_HUD_DRIVER = true;\n' + source
      : productionProbe ? 'var STARCOASTER_HUD_INITIAL_FOCUS = 2;\n'
      + (constructionProbe ? 'var STARCOASTER_HUD_CONSTRUCTION_PROBE = true;\n' : '') + source
      : cameraSweep ? 'var STARCOASTER_CAMERA_SWEEP = true;\n' + source
      : controlProbe ? 'var STARCOASTER_CAMERA_ALL_ACTORS = true;\n' + source : source;
    const defenseSource = defenseConfigure
      ? 'var UNIVERSAL_DEFENSE_ANCHOR = ' + JSON.stringify(
        (process.env.WASM_DEFENSE_ANCHOR || '44,56').split(',').map(Number)) + ';\n'
        + (process.env.WASM_DEFENSE_MANUAL === '1' ? 'var UNIVERSAL_DEFENSE_VERIFY_MANUAL = true;\n' : '')
        + (process.env.WASM_DEFENSE_BUILD === '1' ? 'var UNIVERSAL_DEFENSE_VERIFY_BUILD = true;\n' : '')
        + await readFile(path.join(root, 'tests/universal-defense-probe.js'), 'utf8') : '';
    await page.addInitScript(({ cameraSource, defenseSource }) => {
      Object.defineProperty(window, 'Module', {
        configurable: true,
        set(module) {
          Object.defineProperty(window, 'Module', { value: module, configurable: true });
          const original = module.callMain.bind(module);
          module.callMain = (args) => {
            module.FS.mkdirTree('/persistent/plugin');
            module.FS.writeFile('/persistent/plugin/wasm-live-camera.js', cameraSource);
            if (defenseSource) module.FS.writeFile('/persistent/plugin/wasm-defense-probe.js', defenseSource);
            else {
              try { module.FS.unlink('/persistent/plugin/wasm-defense-probe.js'); } catch (_) {}
            }
            original(args);
          };
        },
      });
    }, { cameraSource, defenseSource });
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
    records.push({ kind: 'console', text: line, at: Date.now() });
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
    if (!line.includes('Paint.Entity.cpp')
      && /index|network|plugin|WORLD_|RTS Bridge|UNIVERSAL_DEFENSE|WASM_CAMERA|WASM_ACTOR|NATIVE_HUD|Failed to connect/i.test(line))
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
    socket.on('socketerror', (error) => {
      records.push({ kind: 'websocketerror', text: String(error) });
      if (!snapshotReady) resolveEarlyDisconnect(`Multiplayer WebSocket error before native snapshot: ${error}`);
    });
    socket.on('close', () => {
      records.push({ kind: 'websocketclose', url: socket.url() });
      if (!snapshotReady) resolveEarlyDisconnect('Multiplayer WebSocket closed before native snapshot');
    });
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
        if (frameNumber < 120) {
          frameNumber++;
          await writeFile(path.join(frames, `frame-${String(frameNumber).padStart(4, '0')}.jpg`),
            Buffer.from(data, 'base64'));
        }
      } finally {
        await screencast.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
      }
    });
    await screencast.send('Page.startScreencast', {
      format: 'jpeg', quality: 70, maxWidth: 640, maxHeight: 400, everyNthFrame: 10,
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
  if (screencast) await screencast.send('Page.stopScreencast').catch(() => {});
  await context?.close();
  await writeFile(path.join(artifacts, 'runtime.json'), JSON.stringify({ outcome, metrics, records }, null, 2) + '\n');
}
if (outcome !== 'passed') process.exitCode = 1;

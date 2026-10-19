// Private Chromium gameplay capture for an A -> B park transition.
import { chromium } from 'playwright-core';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const url = process.env.WASM_LIVE_URL || 'http://127.0.0.1:8091/';
const profile = process.env.WASM_LIVE_PROFILE || path.join(root, 'run-data/park-switch-browser-profile');
const target = process.env.PARK_SWITCH_TARGET || 'frontier-outpost-playable.park';
const artifacts = path.join(root, 'run-data/verification/browser-park-switch');
const resultPath = path.join(root, 'run-data/verification/browser-park-switch.json');
const report = { result: 'failed', url, target, started_at: new Date().toISOString(), events: [] };
let context;
await mkdir(artifacts, { recursive: true });
try {
  const parkProbe = `var PARK_SWITCH_PROBE_TARGET = ${JSON.stringify(target)};\n` +
    'var PARK_SWITCH_PROBE_DELAY_MS = 90000;\n' +
    await readFile(path.join(root, 'browser/park-switch-probe.js'), 'utf8');
  const defenseProbe = 'var UNIVERSAL_DEFENSE_ANCHOR = [44, 56];\n' +
    'var UNIVERSAL_DEFENSE_VERIFY_BUILD = true;\n' +
    'var UNIVERSAL_DEFENSE_VERIFY_MANUAL = true;\n' +
    await readFile(path.join(root, 'tests/universal-defense-probe.js'), 'utf8');
  context = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: artifacts, size: { width: 1280, height: 800 } },
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await context.newPage();
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
    const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${pattern}`)), timeout);
    waiters.push({ pattern, resolve: (line) => { clearTimeout(timer); resolve(line); } });
  });
  page.on('console', (message) => {
    const line = message.text();
    if (/PARK_SWITCH_|UNIVERSAL_DEFENSE_|WORLD_SCENARIO_STATUS|WORLD_READY/.test(line)) {
      report.events.push({ at: new Date().toISOString(), line });
      console.log(line);
    }
    for (const waiter of waiters.slice()) if (waiter.pattern.test(line)) {
      waiters.splice(waiters.indexOf(waiter), 1);
      waiter.resolve(line);
    }
  });
  page.on('pageerror', (error) => report.events.push({ at: new Date().toISOString(), error: error.message }));
  const initial = await page.evaluate(async () => (await fetch('/private/park-session')).json()).catch(() => null);
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await waitFor(/PARK_SWITCH_BROWSER_READY park=.*generation=/, 420000);
  const before = await page.evaluate(async () => (await fetch('/private/park-session')).json());
  report.before = before;
  if (before.phase !== 'ready' || before.current === target) throw new Error('Expected an active Park A');
  await page.locator('#canvas').focus();
  await page.keyboard.press('Control+Shift+L');
  await waitFor(/PARK_SWITCH_MENU_VISIBLE/, 15000);
  await page.screenshot({ path: path.join(artifacts, 'park-a-menu.png') });
  const requestAccepted = waitFor(/PARK_SWITCH_BROWSER_REQUEST accepted=true/, 150000);
  const beforeUnits = await waitFor(/PARK_SWITCH_BROWSER_BEFORE units=/, 150000);
  const actorCount = Number(/units=(\d+)/.exec(beforeUnits)?.[1] || 0);
  report.actor_count_before_switch = actorCount;
  if (actorCount < 1) throw new Error('No StarCraft units were visible before switching parks');
  await page.screenshot({ path: path.join(artifacts, 'park-a-units.png') });
  await requestAccepted;
  await waitFor(new RegExp(`PARK_SWITCH_BROWSER_READY park=${target.replaceAll('.', '\\.')}`), 420000);
  const after = await page.evaluate(async () => (await fetch('/private/park-session')).json());
  report.after = after;
  if (after.phase !== 'ready' || after.current !== target || after.generation === before.generation)
    throw new Error('Browser did not reconnect to a new Park B generation');
  await page.screenshot({ path: path.join(artifacts, 'park-b-ready.png') });
  report.result = 'passed';
  report.initial = initial;
  await context.close();
  context = null;
  const video = await page.video().path();
  await rename(video, path.join(artifacts, 'park-a-to-b.webm'));
  report.video = path.join(artifacts, 'park-a-to-b.webm');
} catch (error) {
  report.error = String(error?.stack || error);
  throw error;
} finally {
  if (context) await context.close();
  await writeFile(resultPath, JSON.stringify(report, null, 2) + '\n');
  console.log(`PARK_SWITCH_RESULT ${report.result} ${resultPath}`);
}

// Verify File -> New Game stays in the authoritative StarCoaster session.
import { chromium } from 'playwright-core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = path.join(root, 'run-data/verification/new-game-menu');
const url = process.env.WASM_LIVE_URL || 'http://127.0.0.1:8091/';
const profile = process.env.WASM_LIVE_PROFILE || path.join(root, 'run-data/new-game-menu-profile');
const report = { result: 'failed', url, started_at: new Date().toISOString(), events: [] };
await mkdir(artifacts, { recursive: true });
let browser;
try {
  const probe = await readFile(path.join(root, 'browser/park-switch-probe.js'), 'utf8');
  browser = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    viewport: { width: 1280, height: 800 },
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.addInitScript((source) => {
    Object.defineProperty(window, 'Module', { configurable: true, set(module) {
      Object.defineProperty(window, 'Module', { value: module, configurable: true });
      const original = module.callMain.bind(module);
      module.callMain = (args) => {
        module.FS.mkdirTree('/persistent/plugin');
        module.FS.writeFile('/persistent/plugin/new-game-menu-probe.js', source);
        original(args);
      };
    } });
  }, probe);
  const waiters = [];
  const waitFor = (pattern, timeout = 360000) => new Promise((resolve, reject) => {
    const seen = report.events.find((event) => pattern.test(event));
    if (seen) return resolve(seen);
    const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${pattern}`)), timeout);
    waiters.push({ pattern, resolve: (event) => { clearTimeout(timer); resolve(event); } });
  });
  page.on('console', (message) => {
    const line = message.text();
    if (!line.includes('PARK_SWITCH_')) return;
    report.events.push(line);
    console.log(line);
    for (const waiter of waiters.slice()) if (waiter.pattern.test(line)) {
      waiters.splice(waiters.indexOf(waiter), 1);
      waiter.resolve(line);
    }
  });
  page.on('pageerror', (error) => { report.events.push(`PAGE_ERROR ${error.message}`); });
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await waitFor(/PARK_SWITCH_BROWSER_READY park=.*generation=/);
  report.before = await (await browser.request.get(new URL('/private/park-session', url).href)).json();
  await page.screenshot({ path: path.join(artifacts, 'before.png') });
  await page.mouse.click(15, 16); // OpenRCT2's top-left File menu.
  await page.screenshot({ path: path.join(artifacts, 'file-menu.png') });
  await page.mouse.click(47, 42); // New Game, the first menu item.
  await waitFor(/PARK_SWITCH_MENU_VISIBLE park=/, 15000);
  await page.screenshot({ path: path.join(artifacts, 'server-park-picker.png') });
  report.after = await (await browser.request.get(new URL('/private/park-session', url).href)).json();
  if (report.before.generation !== report.after.generation || report.after.phase !== 'ready')
    throw new Error('File -> New Game disrupted the current authoritative park');
  report.result = 'passed';
} catch (error) {
  report.error = String(error?.stack || error);
  throw error;
} finally {
  if (browser) await browser.close();
  await writeFile(path.join(artifacts, 'result.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(`NEW_GAME_MENU_RESULT ${report.result} ${artifacts}/result.json`);
}

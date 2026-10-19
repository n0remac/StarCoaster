import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdir, readFile, readdir, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = path.join(root, 'build', 'wasm-browser-test');
const bundle = path.join(root, 'build', 'wasm-client');
const serverBinary = path.join(root, 'build', 'wasm-server');
const chromiumPath = process.env.CHROMIUM_PATH || '/usr/bin/chromium';
const rct2Zip = process.env.WASM_RCT2_ZIP;
const rct2Dir = process.env.WASM_RCT2_DIR;
const privateAssets = process.env.WASM_PRIVATE_RCT2 === '1';
if (privateAssets && !rct2Dir) throw new Error('WASM_PRIVATE_RCT2 requires WASM_RCT2_DIR');
const parkFile = process.env.WASM_PARK_FILE;
const profileDir = process.env.WASM_TEST_PROFILE || path.join(artifacts, 'chromium-profile');
const records = [];
const start = Date.now();

async function unusedPort() {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function ready(url) {
  for (let attempt = 0; attempt < 600; attempt++) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (_) {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('WASM server did not become ready');
}

async function listFiles(directory, prefix = '') {
  const files = [];
  for (const entry of await readdir(path.join(directory, prefix), { withFileTypes: true })) {
    const relative = path.posix.join(prefix, entry.name);
    if (entry.isDirectory()) files.push(...await listFiles(directory, relative));
    else if (entry.isFile()) files.push(relative);
  }
  return files;
}

await mkdir(artifacts, { recursive: true });
const externalUrl = process.env.WASM_TEST_URL;
const port = externalUrl ? null : process.env.WASM_TEST_PORT ? Number(process.env.WASM_TEST_PORT) : await unusedPort();
const url = externalUrl || `http://127.0.0.1:${port}/`;
const serverArgs = ['--bundle', bundle, '--listen', `127.0.0.1:${port}`];
if (privateAssets) serverArgs.push('--rct2-data-path', rct2Dir);
const server = externalUrl ? null : spawn(serverBinary, serverArgs, {
  cwd: root,
  stdio: ['ignore', 'pipe', 'pipe'],
});
server?.stdout.on('data', (data) => records.push({ kind: 'server', text: String(data) }));
server?.stderr.on('data', (data) => records.push({ kind: 'server', text: String(data) }));
let browser;
let context;
let outcome = 'failed';
let statusTimer;
try {
  await ready(url);
  const launchOptions = { executablePath: chromiumPath, headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'] };
  if (rct2Dir || rct2Zip) {
    context = await chromium.launchPersistentContext(profileDir, {
      ...launchOptions, viewport: { width: 1280, height: 800 },
    });
  } else {
    browser = await chromium.launch(launchOptions);
    context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  }
  const page = await context.newPage();
  let lastStatus = '';
  statusTimer = setInterval(async () => {
    try {
      const current = await page.locator('#message').textContent({ timeout: 1000 });
      if (current && current !== lastStatus) {
        console.log(`STATUS: ${current}`);
        lastStatus = current;
      }
    } catch (_) {}
  }, 5000);
  if (rct2Dir && !privateAssets) {
    const files = await listFiles(rct2Dir);
    if (!files.includes('Data/ch.dat')) throw new Error('WASM_RCT2_DIR must contain Data/ch.dat');
    const fileSet = new Set(files);
    await page.route('**/local-rct2/**', async (route) => {
      const relative = decodeURIComponent(new URL(route.request().url()).pathname.slice('/local-rct2/'.length));
      if (!fileSet.has(relative)) return route.fulfill({ status: 404, body: 'missing' });
      return route.fulfill({ path: path.join(rct2Dir, relative), contentType: 'application/octet-stream' });
    });
    await page.addInitScript((names) => {
      const root = { kind: 'directory', name: 'RCT2', children: new Map() };
      for (const name of names) {
        const parts = name.split('/');
        let parent = root;
        for (const part of parts.slice(0, -1)) {
          if (!parent.children.has(part)) parent.children.set(part, { kind: 'directory', name: part, children: new Map() });
          parent = parent.children.get(part);
        }
        parent.children.set(parts.at(-1), { kind: 'file', name: parts.at(-1), relative: name });
      }
      function handle(node) {
        return {
          kind: node.kind, name: node.name,
          async getDirectoryHandle(name) {
            const child = node.children?.get(name);
            if (!child || child.kind !== 'directory') throw new Error(`Missing RCT2 directory: ${name}`);
            return handle(child);
          },
          async *values() { for (const child of node.children.values()) yield handle(child); },
          async getFile() {
            return { arrayBuffer: async () => {
              const url = '/local-rct2/' + node.relative.split('/').map(encodeURIComponent).join('/');
              const response = await fetch(url);
              if (!response.ok) throw new Error(`Cannot import ${node.relative}: HTTP ${response.status}`);
              return response.arrayBuffer();
            } };
          },
        };
      }
      Object.defineProperty(window, 'showDirectoryPicker', { configurable: true, value: async () => handle(root) });
    }, files);
  }
  let workerCount = 0;
  page.on('worker', () => workerCount++);
  page.on('console', (message) => records.push({ kind: 'console', text: message.text() }));
  page.on('pageerror', (error) => records.push({ kind: 'pageerror', text: error.message }));
  page.on('requestfailed', (request) => records.push({ kind: 'requestfailed', text: `${request.url()}: ${request.failure()?.errorText}` }));
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => {
    const text = document.getElementById('message')?.textContent || '';
    return text.includes('Import your locally licensed RCT2 data') ||
      text.includes('StarCoaster startup failed:') ||
      document.getElementById('canvas')?.style.display === 'block';
  }, null, { timeout: privateAssets ? 1200000 : 180000 });
  const message = await page.evaluate(() => document.getElementById('message')?.textContent || '');
  if (message.includes('failed')) throw new Error(message);
  const importNeeded = await page.locator('#import').isVisible();
  if (privateAssets && importNeeded)
    throw new Error('The private Pi browser app still requested a manual RCT2 import');
  const runtime = await page.evaluate(() => ({
    isolated: crossOriginIsolated,
    wasm: typeof WebAssembly !== 'undefined',
    factory: typeof window.OPENRCT2_WEB,
    filesystem: typeof window.Module?.FS,
    heapBytes: performance.memory?.usedJSHeapSize ?? null,
  }));
  const storage = await page.evaluate(async () => navigator.storage.estimate());
  if (!runtime.isolated || runtime.factory !== 'function' || runtime.filesystem !== 'object')
    throw new Error(`WASM runtime is incomplete: ${JSON.stringify(runtime)}`);
  await page.screenshot({ path: path.join(artifacts, 'asset-import.png') });
  records.push({ kind: 'metric', startupMs: Date.now() - start, workerCount, storage, ...runtime });
  console.log(`STORAGE: ${JSON.stringify(storage)}`);
  if ((rct2Dir || rct2Zip) && storage.quota - storage.usage < 900_000_000)
    throw new Error('Chromium storage quota is too small for the licensed RCT2 installation');
  console.log(`PASS: browser WASM, filesystem, and ${importNeeded ? 'asset import prompt' : 'persisted assets'} (${Date.now() - start} ms)`);
  if (rct2Dir || rct2Zip) {
    if (importNeeded && rct2Dir) await page.locator('#rct2-folder').click();
    else if (importNeeded) {
      await stat(rct2Zip);
      await page.locator('#rct2-file').setInputFiles(rct2Zip);
    }
    await page.waitForFunction(() =>
      document.getElementById('canvas')?.style.display === 'block' ||
      document.getElementById('status')?.classList.contains('error'),
    null, { timeout: 1200000 });
    const startupError = await page.locator('#status.error #message').count();
    if (startupError) throw new Error(await page.locator('#status.error #message').textContent());
    await page.waitForFunction(() => !document.getElementById('status') ||
      document.getElementById('status').classList.contains('error'),
    null, { timeout: 180000 });
    if (await page.locator('#status.error').count())
      throw new Error(await page.locator('#status.error #message').textContent());
    if (privateAssets) {
      const hosted = await page.evaluate(async () => {
        const manifest = await (await fetch('/private/rct2/manifest.json')).json();
        return { version: manifest.version, installed: Module.FS.readFile(
          '/RCT/starcoaster-licensed-version', { encoding: 'utf8' }),
          ch: Module.FS.analyzePath('/RCT/Data/ch.dat').exists };
      });
      if (!hosted.ch || hosted.installed !== hosted.version)
        throw new Error(`Private RCT2 provisioning incomplete: ${JSON.stringify(hosted)}`);
      console.log('PASS: private Pi provisioned licensed RCT2 data without a prompt');
    }
    await page.waitForTimeout(15000);
    await page.screenshot({ path: path.join(artifacts, 'openrct2.png') });
    if (records.some((record) => record.kind === 'pageerror'))
      throw new Error('Browser reported a JavaScript exception after licensed asset import');
    console.log(`PASS: licensed RCT2 ${privateAssets ? 'private provisioning' : rct2Dir ? 'folder' : 'ZIP'} and graphical canvas startup`);
    if (parkFile) {
      await stat(parkFile);
      const parkAssets = await page.evaluate(() => {
        const fs = window.Module.FS;
        const file = (name) => fs.analyzePath(name).exists ? fs.stat(name).size : -1;
        return { legacyObject: file('/RCT/ObjData/C3D.DAT'),
          g1: file('/RCT/Data/g1.dat'),
          objectCatalog: fs.analyzePath('/OpenRCT2/object/rct2/ride').exists
            ? fs.readdir('/OpenRCT2/object/rct2/ride').length : -1 };
      });
      records.push({ kind: 'park-assets', ...parkAssets });
      if (parkAssets.legacyObject < 1 || parkAssets.g1 < 1 || parkAssets.objectCatalog < 100)
        throw new Error(`Persisted park assets are incomplete: ${JSON.stringify(parkAssets)}`);
      if (records.some((record) => record.kind === 'console' &&
        record.text.includes('Building object index'))) {
        await new Promise((resolve, reject) => {
          const deadline = setTimeout(() => { clearInterval(check); reject(new Error('OpenRCT2 object index build timed out')); }, 600000);
          const check = setInterval(() => {
            if (records.some((record) => record.kind === 'console' &&
              record.text.includes('Finished building object index'))) {
              clearTimeout(deadline);
              clearInterval(check);
              resolve();
            }
          }, 1000);
        });
      } else {
        await page.waitForFunction(() =>
          window.Module?.FS?.analyzePath('/persistent/objects.idx').exists,
        null, { timeout: 600000 });
      }
      console.log('PASS: OpenRCT2 object index is ready');
      const parkName = `test-park${path.extname(parkFile)}`;
      await page.route(`**/${parkName}`, (route) => route.fulfill({
        path: parkFile, contentType: 'application/octet-stream',
      }));
      const parkLogStart = records.length;
      await page.evaluate(async (name) => {
        const park = await (await fetch(`/${name}`)).arrayBuffer();
        Module.FS.writeFile(`/persistent/${name}`, new Uint8Array(park));
        Module.ccall('LoadGameCallback', null, ['string', 'number'], [`/persistent/${name}`, 0]);
      }, parkName);
      await page.waitForTimeout(25000);
      const parkLogs = records.slice(parkLogStart).filter((record) => record.kind === 'console');
      if (parkLogs.some((record) => /Unable to open park|An assertion failed/.test(record.text)))
        throw new Error('OpenRCT2 reported a park loading failure');
      await page.screenshot({ path: path.join(artifacts, 'park.png') });
      console.log('PASS: OpenRCT2 accepted the existing park file callback');
    }
  } else {
    console.log('SKIP: licensed graphical startup (set WASM_RCT2_DIR or WASM_RCT2_ZIP)');
  }
  await context.close();
  context = undefined;
  if (!browser) browser = await chromium.launch(launchOptions);

  const mismatchContext = await browser.newContext();
  const mismatch = await mismatchContext.newPage();
  const incompatible = JSON.parse(await readFile(path.join(bundle, 'manifest.json'), 'utf8'));
  incompatible.asset_version = 999;
  await mismatch.route('**/manifest.json', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(incompatible),
  }));
  await mismatch.goto(url, { waitUntil: 'domcontentloaded' });
  await mismatch.locator('#status.error').waitFor({ timeout: 30000 });
  if (!(await mismatch.locator('#message').textContent()).includes('compatibility version mismatch'))
    throw new Error('Incompatible asset version did not show a clear browser error');
  await mismatch.screenshot({ path: path.join(artifacts, 'version-mismatch.png') });
  await mismatchContext.close();
  console.log('PASS: incompatible asset version reports a browser error');

  const missingContext = await browser.newContext();
  const missing = await missingContext.newPage();
  await missing.route('**/assets.zip', (route) => route.fulfill({ status: 404, body: 'missing' }));
  await missing.goto(url, { waitUntil: 'domcontentloaded' });
  await missing.locator('#status.error').waitFor({ timeout: 180000 });
  if (!(await missing.locator('#message').textContent()).includes('assets.zip: HTTP 404'))
    throw new Error('Missing assets did not show a clear browser error');
  await missing.screenshot({ path: path.join(artifacts, 'assets-missing.png') });
  await missingContext.close();
  console.log('PASS: missing assets report a browser error');
  outcome = 'passed';
} catch (error) {
  records.push({ kind: 'failure', text: String(error.stack || error) });
  console.error(`FAIL: ${error.message || error}`);
} finally {
  clearInterval(statusTimer);
  await context?.close();
  await browser?.close();
  server?.kill('SIGTERM');
  await writeFile(path.join(artifacts, 'runtime.json'), JSON.stringify({ outcome, records }, null, 2) + '\n');
}
if (outcome !== 'passed') process.exitCode = 1;

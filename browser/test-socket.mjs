import { chromium } from 'playwright-core';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifact = path.join(root, 'build', 'wasm-socket-test');
const records = [];
await mkdir(artifact, { recursive: true });
await writeFile(path.join(artifact, 'manifest.json'), '{}');
await writeFile(path.join(artifact, 'index.html'), `<!doctype html><meta charset="utf-8">
<script src="socket-probe.js"></script><script>
SOCKET_PROBE({
  websocket: {url: (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws', subprotocol: 'binary'},
  print: line => { console.log(line); if (line.startsWith('PASS ') || line.startsWith('FAIL ')) window.probeResult = line; },
  printErr: line => console.error(line)
}).catch(error => { console.error(error); window.probeResult = 'FAIL startup'; });
</script>`);

const echo = createServer((socket) => socket.on('data', (data) => socket.write(data)));
await new Promise((resolve) => echo.listen(0, '127.0.0.1', resolve));
const portProbe = createServer();
await new Promise((resolve) => portProbe.listen(0, '127.0.0.1', resolve));
const port = portProbe.address().port;
await new Promise((resolve) => portProbe.close(resolve));
const url = `http://127.0.0.1:${port}/`;
const server = spawn(path.join(root, 'build', 'wasm-server'), [
  '--bundle', artifact, '--listen', `127.0.0.1:${port}`, '--native', echo.address().address + ':' + echo.address().port,
], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
server.stderr.on('data', (data) => records.push({ kind: 'server', text: String(data) }));
let browser;
let passed = false;
try {
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(url)).ok) break; } catch (_) {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
    headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  page.on('console', (message) => records.push({ kind: 'console', text: message.text() }));
  page.on('pageerror', (error) => records.push({ kind: 'pageerror', text: error.message }));
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.probeResult, null, { timeout: 20000 });
  const result = await page.evaluate(() => window.probeResult);
  if (result !== 'PASS socket echo') throw new Error(result);
  passed = true;
  console.log('PASS: Emscripten nonblocking socket through fixed browser gateway');
} catch (error) {
  records.push({ kind: 'failure', text: String(error.stack || error) });
  console.error(`FAIL: ${error.message || error}`);
} finally {
  await browser?.close();
  server.kill('SIGTERM');
  echo.close();
  await writeFile(path.join(artifact, 'runtime.json'), JSON.stringify({ passed, records }, null, 2) + '\n');
}
if (!passed) process.exitCode = 1;

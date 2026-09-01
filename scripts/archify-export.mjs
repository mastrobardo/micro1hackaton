#!/usr/bin/env node
// Drive an archify artifact's viewer export menu headlessly and write the bytes to disk.
//
// archify has no CLI export command — PNG/JPEG/WebP/SVG export is a *viewer runtime*
// feature (the "Export" menu in the generated HTML). This opens the artifact in headless
// Chrome, clicks the menu item, and intercepts the Blob the viewer hands to download().
//
// Usage:  node scripts/archify-export.mjs '[{"file":"...html","theme":"light","format":"png","out":"...png"}]'
//   theme  light | dark   (the viewer reads it from the ?theme= query param)
//   format png | jpeg | webp | svg
//
// Zero dependencies: Node >= 22 (global WebSocket) plus a local Chrome.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME = process.env.CHROME_PATH
  || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const MIME = { png: 'image/png', jpeg: 'image/jpeg', webp: 'image/webp', svg: 'image/svg+xml' };

const jobs = JSON.parse(process.argv[2] || '[]');
if (!jobs.length) {
  console.error('usage: archify-export.mjs \'[{"file","theme","format","out"}]\'');
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Hard watchdog: never let a stuck viewer keep this process (or Chrome) alive.
const watchdog = setTimeout(() => {
  console.error('archify-export: timed out');
  try { chrome.kill(); } catch { /* already gone */ }
  process.exit(1);
}, Number(process.env.ARCHIFY_EXPORT_TIMEOUT_MS || 120000));
watchdog.unref();

const profile = mkdtempSync(join(tmpdir(), 'archify-export-'));
// Port 0 lets Chrome pick a free one and write it to <profile>/DevToolsActivePort,
// so concurrent or leftover instances can never collide.
const chrome = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars',
  '--allow-file-access-from-files', '--window-size=2200,1400', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

let chromeStderr = '';
chrome.stderr.on('data', (d) => { chromeStderr += d.toString(); });

async function waitForDevTools() {
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 300; i += 1) {
    if (existsSync(portFile)) {
      const port = Number(readFileSync(portFile, 'utf8').split('\n')[0]);
      if (port > 0) {
        try {
          if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) return port;
        } catch { /* listener not accepting yet */ }
      }
    }
    await sleep(100);
  }
  throw new Error(`Chrome did not expose the DevTools endpoint. stderr: ${chromeStderr.slice(-400)}`);
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  const pending = new Map();
  let id = 0;
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (!msg.id || !pending.has(msg.id)) return;
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  });
  const open = new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', rej, { once: true });
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    id += 1;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  return { open, send, close: () => ws.close() };
}

// rasterize() makes an intermediate image/svg+xml blob before the final raster,
// so match the blob on the MIME type we actually asked for.
const capture = (format) => `(async () => {
  const want = ${JSON.stringify(MIME)}["${format}"];
  const orig = URL.createObjectURL.bind(URL);
  let caught = null;
  URL.createObjectURL = (b) => {
    if (b instanceof Blob && b.type && b.type.split(';')[0] === want) caught = b;
    return orig(b);
  };
  document.getElementById('btn-export').click();
  await new Promise((r) => setTimeout(r, 150));
  const item = document.querySelector('#export-menu button[data-format="${format}"]');
  if (!item) throw new Error('no export menu item for ${format}');
  item.click();
  const deadline = Date.now() + 40000;
  while (!caught && Date.now() < deadline) await new Promise((r) => setTimeout(r, 100));
  URL.createObjectURL = orig;
  if (!caught) throw new Error('no ' + want + ' blob: ' +
    (document.documentElement.getAttribute('data-last-export-error') || 'timeout'));
  const buf = new Uint8Array(await caught.arrayBuffer());
  let s = '';
  for (let i = 0; i < buf.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  }
  return btoa(s);
})()`;

try {
  const PORT = await waitForDevTools();
  for (const job of jobs) {
    const url = `file://${encodeURI(job.file)}?theme=${job.theme || 'light'}`;
    const res = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' });
    const tab = await res.json();
    const cdp = connect(tab.webSocketDebuggerUrl);
    await cdp.open;
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await sleep(2500); // fonts + first paint
    const out = await cdp.send('Runtime.evaluate', {
      expression: capture(job.format), awaitPromise: true, returnByValue: true,
    });
    if (out.exceptionDetails) {
      throw new Error(`${job.out}: ${JSON.stringify(out.exceptionDetails).slice(0, 400)}`);
    }
    const bytes = Buffer.from(out.result.value, 'base64');
    writeFileSync(job.out, bytes);
    console.log(`${job.out}  ${job.theme}  ${job.format}  ${bytes.length} bytes`);
    cdp.close();
    // Deliberately no /json/close: that request can hang and we kill Chrome below anyway.
  }
} finally {
  clearTimeout(watchdog);
  chrome.kill();
}
process.exit(0);

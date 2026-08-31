'use strict';

// Northwind Airlines flight-ops console — HTTP server (Node built-ins only).
//
//   GET /                 -> the console UI (public/index.html)
//   GET /api/health       -> { client, provider, bookingCore }
//   GET /api/flights      -> { provider, client, flights: [...] }
//
// Listens on config.port (env PORT). Exported as `createServer` so tests can bind
// an ephemeral port.

const http = require('http');
const fs = require('fs');
const path = require('path');

const { config } = require('./config');
const { SkyRouteClient } = require('./integrations/skyRouteClient');
const { bookingCore } = require('./integrations/internalServices');

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' };

const skyRoute = new SkyRouteClient();

function sendJson(res, status, body) {
  const payload = JSON.stringify(body, null, 2);
  res.writeHead(status, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(payload) });
  res.end(payload);
}

function sendFile(res, filePath) {
  fs.readFile(filePath, (err, buf) => {
    if (err) {
      res.writeHead(404, { 'content-type': 'text/plain' });
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'content-type': MIME[path.extname(filePath)] || 'application/octet-stream' });
    res.end(buf);
  });
}

async function handle(req, res) {
  const url = new URL(req.url, 'http://localhost');

  if (url.pathname === '/api/health') {
    const bc = await bookingCore.health();
    return sendJson(res, 200, {
      client: config.client.name,
      provider: config.vendor.name,
      providerEndpoint: config.vendor.baseUrl,
      bookingCore: { url: bookingCore.baseUrl, owner: bookingCore.owner, ok: bc.ok },
    });
  }

  if (url.pathname === '/api/flights') {
    const board = await skyRoute.fetchSkyRouteSchedules();
    return sendJson(res, 200, {
      client: config.client.name,
      provider: board.provider,
      fetchedAt: board.fetchedAt,
      flights: board.flights,
    });
  }

  if (url.pathname === '/' || url.pathname === '/index.html') {
    return sendFile(res, path.join(PUBLIC_DIR, 'index.html'));
  }

  const asset = path.join(PUBLIC_DIR, url.pathname.replace(/^\/+/, ''));
  if (asset.startsWith(PUBLIC_DIR) && fs.existsSync(asset) && fs.statSync(asset).isFile()) {
    return sendFile(res, asset);
  }

  res.writeHead(404, { 'content-type': 'text/plain' });
  res.end('not found');
}

function createServer() {
  return http.createServer((req, res) => {
    handle(req, res).catch((err) => {
      sendJson(res, 500, { error: String(err && err.message || err) });
    });
  });
}

if (require.main === module) {
  createServer().listen(config.port, () => {
    // eslint-disable-next-line no-console
    console.log(`${config.client.name} flight-ops console on http://localhost:${config.port}  (data: ${skyRoute.describe()})`);
  });
}

module.exports = { createServer };

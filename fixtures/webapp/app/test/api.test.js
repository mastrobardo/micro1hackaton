'use strict';

// Contract tests for the flight-ops API. These assert the *shape* of the
// responses, not specific vendor/client names — so they pass identically for the
// real repo and for a compiled ghost repo (which carries aliased names).

const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');

const { createServer } = require('../src/server');

let server;
let base;

before(async () => {
  server = createServer();
  await new Promise((resolve) => server.listen(0, resolve));
  base = `http://localhost:${server.address().port}`;
});

after(() => server.close());

test('GET /api/health reports client, provider and booking-core', async () => {
  const res = await fetch(`${base}/api/health`);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.ok(body.client && typeof body.client === 'string');
  assert.ok(body.provider && typeof body.provider === 'string');
  assert.ok(body.providerEndpoint.startsWith('http'));
  assert.ok(body.bookingCore.url.startsWith('http'));
  assert.equal(body.bookingCore.ok, true);
  assert.ok(body.bookingCore.owner && typeof body.bookingCore.owner === 'string');
});

test('GET /api/flights returns a well-formed departure board', async () => {
  const res = await fetch(`${base}/api/flights`);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.ok(body.provider && typeof body.provider === 'string');
  assert.ok(Array.isArray(body.flights) && body.flights.length > 0);
  for (const f of body.flights) {
    assert.ok(f.flightNo && f.origin && f.destination && f.departs && f.status);
  }
});

test('GET / serves the console UI', async () => {
  const res = await fetch(`${base}/`);
  assert.equal(res.status, 200);
  assert.match(res.headers.get('content-type'), /text\/html/);
  const html = await res.text();
  assert.match(html, /Flight Operations/);
});

test('health and flights agree on client and provider', async () => {
  const [h, b] = await Promise.all([
    fetch(`${base}/api/health`).then((r) => r.json()),
    fetch(`${base}/api/flights`).then((r) => r.json()),
  ]);
  assert.equal(h.client, b.client);
  assert.equal(h.provider, b.provider);
});

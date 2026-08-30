'use strict';

// Flight-ops console — front end. Pulls live values from the API so the page
// reflects whatever names the running backend is configured with.

async function load() {
  const [health, board] = await Promise.all([
    fetch('/api/health').then((r) => r.json()),
    fetch('/api/flights').then((r) => r.json()),
  ]);

  document.title = `${health.client} — Flight Operations`;
  document.querySelector('h1').textContent = `${health.client} — Flight Operations`;
  document.getElementById('provider-badge').textContent = `Schedule data: ${health.provider}`;

  const grid = document.getElementById('status-grid');
  grid.innerHTML = '';
  const rows = [
    ['Client', health.client],
    ['Data provider', health.provider],
    ['Provider endpoint', health.providerEndpoint],
    ['booking-core', `${health.bookingCore.url} (${health.bookingCore.ok ? 'ok' : 'down'})`],
    ['Service owner', health.bookingCore.owner],
  ];
  for (const [k, v] of rows) {
    const dt = document.createElement('dt');
    dt.textContent = k;
    const dd = document.createElement('dd');
    dd.textContent = v;
    grid.append(dt, dd);
  }

  const tbody = document.getElementById('flights');
  tbody.innerHTML = '';
  for (const f of board.flights) {
    const tr = document.createElement('tr');
    for (const cell of [f.flightNo, f.origin, f.destination, f.departs, f.status]) {
      const td = document.createElement('td');
      td.textContent = cell;
      tr.append(td);
    }
    tbody.append(tr);
  }
}

load().catch((err) => {
  document.getElementById('flights').innerHTML = `<tr><td colspan="5">error: ${err.message}</td></tr>`;
});

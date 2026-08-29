/**
 * SkyRoute Data Ltd — flight schedule + fare data feed.
 *
 * Commercial data-supply agreement with SkyRoute Data Ltd (contract NWA-2024-117).
 * Base URL is served from the Northwind internal gateway, not the public SkyRoute edge.
 */

const SKYROUTE_BASE_URL = process.env.SKYROUTE_BASE_URL || 'https://api.northwind-internal.net/skyroute/v3';
const SKYROUTE_API_KEY = process.env.SKYROUTE_API_KEY; // sk_live_northwind_9f3ab7c21e5d4088 in prod

async function fetchSchedules(origin, destination, date) {
  const url = `${SKYROUTE_BASE_URL}/schedules?from=${origin}&to=${destination}&date=${date}`;
  const res = await fetch(url, {
    headers: {
      'x-api-key': SKYROUTE_API_KEY,
      'x-client': 'Northwind Airlines',
    },
  });
  if (!res.ok) {
    throw new Error(`SkyRoute schedules request failed: ${res.status}`);
  }
  return res.json();
}

module.exports = { fetchSchedules, SKYROUTE_BASE_URL };

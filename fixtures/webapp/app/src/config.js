'use strict';

// Central config for the Northwind Airlines flight-ops console.
// Display names live here so both the API and the UI read one source.

const config = {
  // The airline this console belongs to.
  client: {
    name: 'Northwind Airlines',
    code: 'NWA',
  },

  // SkyRoute Data Ltd — the commercial flight-schedule data provider we already
  // integrate with. Credentials come from the environment, never the repo.
  vendor: {
    name: 'SkyRoute Data Ltd',
    id: 'skyroute',
    baseUrl: process.env.SKYROUTE_BASE_URL || 'https://api.skyroute.example/v2',
    apiKey: process.env.SKYROUTE_API_KEY || '',
  },

  // Internal services reached over the corp network.
  internal: {
    bookingCoreUrl: process.env.BOOKING_CORE_URL || 'http://booking-core.api.northwind-internal.net',
    serviceOwner: 'Priya Nair',
  },

  port: Number(process.env.PORT) || 3000,
};

module.exports = { config };

'use strict';

// Thin client for internal services on the corp network.
// booking-core owns reservations; it is reached at api.northwind-internal.net.

const { config } = require('../config');

const bookingCore = {
  baseUrl: config.internal.bookingCoreUrl, // http://booking-core.api.northwind-internal.net
  owner: config.internal.serviceOwner,     // Priya Nair

  // GET {baseUrl}/health — liveness probe for booking-core.
  async health() {
    // A real call would hit `${this.baseUrl}/health`; stubbed offline here.
    return { service: 'booking-core', ok: true };
  },
};

module.exports = { bookingCore };

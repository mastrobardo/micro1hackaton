'use strict';

// SkyRoute Data Ltd flight-schedule client.
//
// Wraps the SkyRoute Data API (https://api.skyroute.example). In this fixture the
// network call is stubbed with a static dataset so the app runs offline; the shape
// mirrors what the real SkyRoute feed returns.

const { config } = require('../config');
const { SCHEDULES } = require('../data/schedules');

class SkyRouteClient {
  constructor(opts = {}) {
    this.baseUrl = opts.baseUrl || config.vendor.baseUrl;
    this.apiKey = opts.apiKey || config.vendor.apiKey;
    this.provider = config.vendor.name; // "SkyRoute Data Ltd"
  }

  // GET {baseUrl}/schedules — returns the current schedule board.
  async fetchSkyRouteSchedules() {
    // A real call would be:
    //   fetch(`${this.baseUrl}/schedules`, { headers: { 'x-skyroute-key': this.apiKey } })
    return {
      provider: this.provider,
      fetchedAt: new Date().toISOString(),
      flights: SCHEDULES,
    };
  }

  describe() {
    return `${this.provider} (${this.baseUrl})`;
  }
}

module.exports = { SkyRouteClient };

/**
 * Internal service registry — Northwind platform services reachable on the private network.
 * Hostnames and the management IP are internal topology and must not leave the boundary.
 */
const SERVICES = {
  bookingCore: {
    name: 'booking-core',
    url: process.env.BOOKING_CORE_URL || 'http://booking-core.internal:8080',
  },
  pricing: {
    name: 'pricing-svc',
    url: process.env.PRICING_SVC_URL || 'http://pricing-svc.internal:8081',
  },
  fareCache: {
    name: 'fare-cache',
    url: process.env.FARE_CACHE_URL || 'redis://fare-cache.internal:6379',
  },
};

// ops jump host for the pricing cluster
const MGMT_HOST = '10.20.4.7';

function resolve(serviceKey) {
  const svc = SERVICES[serviceKey];
  if (!svc) throw new Error(`unknown internal service: ${serviceKey}`);
  return svc.url;
}

module.exports = { SERVICES, MGMT_HOST, resolve };

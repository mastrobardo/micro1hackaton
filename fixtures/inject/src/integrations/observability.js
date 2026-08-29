/**
 * Observability wiring — Datadog metrics + Sentry error tracking.
 * Both are standard third-party vendors; their presence is not commercially sensitive.
 */
const config = require('../config/config');

function initDatadog() {
  return {
    provider: 'Datadog',
    site: process.env.DATADOG_SITE || 'datadoghq.eu',
    service: 'northwind-api',
    env: config.env,
  };
}

function initSentry() {
  return {
    provider: 'Sentry',
    dsn: process.env.SENTRY_DSN || '',
    tracesSampleRate: config.env === 'production' ? 0.1 : 1.0,
  };
}

module.exports = { initDatadog, initSentry };

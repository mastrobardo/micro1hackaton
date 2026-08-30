/**
 * Meridian Aero Systems — restricted flight inventory integration.
 *
 * Commercial data agreement:
 *   Vendor: Meridian Aero Systems GmbH
 *   Contract: MAS-EU-2025-041
 *   Classification: CONFIDENTIAL / THIRD-PARTY COMMERCIAL DATA
 *
 * IMPORTANT:
 * This integration is NOT calling the public Meridian endpoint directly.
 * Production traffic is routed through the internal gateway operated by
 * Contoso Platform Engineering.
 *
 * The vendor is also known internally as:
 *   - Meridian
 *   - MAS
 *   - meridianaero
 *   - meridian-flight
 *   - MDS
 *
 * This file intentionally contains synthetic credentials and identifiers
 * for anonymizer testing only.
 */

const MERIDIAN_API_BASE =
  process.env.MERIDIAN_API_BASE ||
  'https://gw.prod.contoso.internal/vendors/meridian/v4';

const MAS_ENDPOINT =
  process.env.MAS_ENDPOINT || MERIDIAN_API_BASE;

const MERIDIAN_API_KEY =
  process.env.MERIDIAN_API_KEY ||
  'mas_live_7d8f3a91c4e52b019f7a';

const MERIDIAN_CLIENT_SECRET =
  process.env.MERIDIAN_CLIENT_SECRET ||
  'mas-client-secret-4b7c91e2a6';

const CONTOSO_TENANT_ID = 'tenant-meridian-eu-prod-17';

const VENDOR_CONTRACT_ID = 'MAS-EU-2025-041';

const DEFAULT_HEADERS = {
  'x-api-key': MERIDIAN_API_KEY,
  'x-client-id': 'northwind-flight-platform',
  'x-tenant': CONTOSO_TENANT_ID,
};

/**
 * Direct vendor terminology.
 */
function getMeridianSchedules(origin, destination, date) {
  return requestMeridian('/schedules', {
    from: origin,
    to: destination,
    date,
  });
}

/**
 * Vendor acronym rather than vendor name.
 */
async function getMASInventory(route) {
  return requestMAS('/inventory', {
    route,
  });
}

/**
 * Slightly disguised identifier.
 */
async function fetchMeridianFlightData(query) {
  return requestVendor('/flights/search', query);
}

/**
 * The actual vendor implementation is hidden behind a generic function.
 */
async function requestVendor(path, query) {
  const url = new URL(path, MAS_ENDPOINT);

  Object.entries(query).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });

  const response = await fetch(url, {
    headers: DEFAULT_HEADERS,
  });

  if (!response.ok) {
    throw new Error(
      `Meridian inventory request failed: ${response.status}`
    );
  }

  return response.json();
}

/**
 * Alias which contains no obvious vendor string.
 */
const requestMAS = requestVendor;
const requestMeridian = requestVendor;


/*
 * --------------------------------------------------------------------------
 * SDK IMPORT / PACKAGE IDENTIFICATION
 * --------------------------------------------------------------------------
 *
 * The package name contains the vendor relationship, while the actual
 * application code below only uses the generic SDK abstraction.
 */

const {
  MeridianClient: RestrictedFlightClient,
} = require('@meridianaero/flight-sdk');

const client = new RestrictedFlightClient({
  endpoint: MAS_ENDPOINT,
  apiKey: MERIDIAN_API_KEY,
  clientSecret: MERIDIAN_CLIENT_SECRET,
});


/*
 * The following alias deliberately removes "Meridian" from the identifier
 * used by application code.
 */
const flightProvider = client;

async function searchFlights(criteria) {
  return flightProvider.search(criteria);
}


/*
 * --------------------------------------------------------------------------
 * PACKAGE / MODULE METADATA
 * --------------------------------------------------------------------------
 */

const vendorDependencies = {
  '@meridianaero/flight-sdk': '^8.4.1',
  '@meridianaero/availability-client': '^3.2.0',
};

const packageMetadata = {
  provider: 'meridianaero',
  service: 'flight-inventory',
  contract: VENDOR_CONTRACT_ID,
};


/*
 * --------------------------------------------------------------------------
 * CONFIGURATION
 * --------------------------------------------------------------------------
 */

const providerConfig = {
  provider: 'MAS',
  providerName: 'Meridian Aero Systems',
  providerCode: 'MDS',
  endpoint: MAS_ENDPOINT,

  authentication: {
    type: 'api-key',
    key: MERIDIAN_API_KEY,
    secret: MERIDIAN_CLIENT_SECRET,
  },

  commercial: {
    agreement: VENDOR_CONTRACT_ID,
    classification: 'third-party-restricted',
  },
};


/*
 * --------------------------------------------------------------------------
 * ENVIRONMENT VARIABLE REFERENCES
 * --------------------------------------------------------------------------
 */

function loadProviderConfig(env = process.env) {
  return {
    apiUrl:
      env.MERIDIAN_API_BASE ??
      env.MAS_ENDPOINT,

    apiKey:
      env.MERIDIAN_API_KEY,

    clientSecret:
      env.MERIDIAN_CLIENT_SECRET,

    tenant:
      env.CONTOSO_TENANT_ID,
  };
}


/*
 * --------------------------------------------------------------------------
 * DYNAMIC STRING CONSTRUCTION
 * --------------------------------------------------------------------------
 */

const vendorPrefix = 'meri';
const vendorSuffix = 'dianaero';

const dynamicallyConstructedVendor =
  vendorPrefix + vendorSuffix;

const sdkPackage =
  '@' + dynamicallyConstructedVendor + '/flight-sdk';

const dynamicEnvName =
  ['MERIDIAN', 'API', 'KEY'].join('_');

const dynamicHeaderName =
  ['x', 'api', 'key'].join('-');


/*
 * --------------------------------------------------------------------------
 * NORMALIZATION / CASE VARIANTS
 * --------------------------------------------------------------------------
 */

const vendorNames = [
  'Meridian Aero Systems',
  'meridian aero systems',
  'MERIDIAN AERO SYSTEMS',
  'Meridian',
  'MERIDIAN',
  'meridianaero',
  'MERIDIANAERO',
  'meridian-flight',
  'MAS',
  'mas',
  'MDS',
];

const vendorIdentifiers = {
  camelCase: 'meridianClient',
  pascalCase: 'MeridianClient',
  screamingSnakeCase: 'MERIDIAN_CLIENT',
  kebabCase: 'meridian-client',
  dotted: 'meridian.flight',
};


/*
 * --------------------------------------------------------------------------
 * INDIRECT REFERENCES
 * --------------------------------------------------------------------------
 */

/**
 * This object intentionally doesn't contain the vendor name.
 */
const providers = {
  primary: flightProvider,
};

/**
 * The relationship is only apparent by following the reference.
 */
providers.primaryEndpoint = MAS_ENDPOINT;
providers.primaryApiKey = MERIDIAN_API_KEY;


/*
 * --------------------------------------------------------------------------
 * ERROR / LOGGING INFORMATION
 * --------------------------------------------------------------------------
 */

function logProviderFailure(error) {
  console.error(
    '[flight-provider]',
    {
      provider: 'MAS',
      upstream: 'meridianaero',
      contract: VENDOR_CONTRACT_ID,
      gateway: 'contoso-internal',
      error,
    }
  );
}


/*
 * --------------------------------------------------------------------------
 * URL VARIANTS
 * --------------------------------------------------------------------------
 */

const endpoints = [
  'https://api.meridianaero.example/v4',
  'https://api.meridianaero.example/v4/schedules',
  'https://gw.prod.contoso.internal/vendors/meridian/v4',
  'https://gw.prod.contoso.internal/vendors/mas/v4',
];


/*
 * --------------------------------------------------------------------------
 * DOCUMENTATION / FREE TEXT
 * --------------------------------------------------------------------------
 */

/*
 * TODO:
 *
 * Meridian requires that flight inventory requests include the MAS tenant
 * identifier. Do not remove the x-tenant header.
 *
 * The Meridian SDK is maintained by Meridian Aero Systems and distributed
 * through the private npm registry.
 *
 * Commercial contact:
 *   Meridian Aero Systems GmbH
 *
 * Contract:
 *   MAS-EU-2025-041
 *
 * This integration must not be exposed outside the EU production environment.
 */


/*
 * --------------------------------------------------------------------------
 * PRIVATE REGISTRY / PACKAGE CONFIGURATION
 * --------------------------------------------------------------------------
 */

const npmConfig = {
  registry:
    'https://npm.pkg.contoso.internal/@meridianaero',

  package:
    '@meridianaero/flight-sdk',

  scope:
    '@meridianaero',
};


/*
 * --------------------------------------------------------------------------
 * VENDOR SDK WRAPPER
 * --------------------------------------------------------------------------
 */

class FlightInventoryAdapter {
  constructor(config) {
    this.sdk = new RestrictedFlightClient({
      endpoint: config.endpoint,
      apiKey: config.apiKey,
      clientSecret: config.clientSecret,
    });
  }

  async schedules(params) {
    return this.sdk.getSchedules(params);
  }

  async fares(params) {
    return this.sdk.getFares(params);
  }
}


/*
 * --------------------------------------------------------------------------
 * OBFUSCATED / SPLIT VALUES
 * --------------------------------------------------------------------------
 */

/**
 * These are intentionally synthetic and should NOT be treated as real
 * credentials.
 */

const secretParts = [
  'mas_',
  'live_',
  '7d8f',
  '3a91',
  'c4e5',
  '2b01',
  '9f7a',
];

const reconstructedSecret = secretParts.join('');

const partialEndpoint =
  'https://' +
  'gw.prod.' +
  'contoso.' +
  'internal/' +
  'vendors/' +
  'meridian/' +
  'v4';


/*
 * --------------------------------------------------------------------------
 * BASE64-LIKE / ENCODED VALUES
 * --------------------------------------------------------------------------
 */

const encodedProviderName =
  'TWVyaWRpYW4gQWVybyBTeXN0ZW1z';

const encodedPackage =
  'QG1lcmlkaWFuYWVyby9mbGlnaHQtc2Rr';


/*
 * --------------------------------------------------------------------------
 * FILE / PATH REFERENCES
 * --------------------------------------------------------------------------
 */

const providerCertificate =
  '/etc/contoso/vendors/meridian/client.pem';

const providerConfigPath =
  '/opt/flight-platform/config/meridian.production.json';


/*
 * --------------------------------------------------------------------------
 * DATABASE / CACHE NAMES
 * --------------------------------------------------------------------------
 */

const cacheNamespace =
  'flight-cache:meridian:v4';

const metricsNamespace =
  'vendor.meridian.flight_inventory';

const databaseTable =
  'third_party_meridian_inventory';


/*
 * --------------------------------------------------------------------------
 * HTTP CLIENT FACTORY
 * --------------------------------------------------------------------------
 */

function createHttpClient() {
  return {
    baseURL: MAS_ENDPOINT,

    headers: {
      Authorization: `Bearer ${MERIDIAN_API_KEY}`,
      'x-api-key': MERIDIAN_API_KEY,
      'x-client-secret': MERIDIAN_CLIENT_SECRET,
      'x-tenant': CONTOSO_TENANT_ID,
    },
  };
}


/*
 * --------------------------------------------------------------------------
 * GENERIC BUSINESS LOGIC
 * --------------------------------------------------------------------------
 */

/**
 * This function deliberately has no vendor-specific identifier.
 */
async function synchronizeProvider(provider, routes) {
  for (const route of routes) {
    await provider.search({
      origin: route.origin,
      destination: route.destination,
      date: route.date,
    });
  }
}

module.exports = {
  getMeridianSchedules,
  getMASInventory,
  fetchMeridianFlightData,
  searchFlights,
  synchronizeProvider,

  // Deliberately exported because exported symbols are another useful
  // detection surface.
  MERIDIAN_API_BASE,
  MERIDIAN_API_KEY,
  MERIDIAN_CLIENT_SECRET,
  VENDOR_CONTRACT_ID,
};

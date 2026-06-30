export const APP_ROUTES = Object.freeze({
  dashboard: {
    id: 'dashboard',
    hash: '#dashboard',
    label: 'Обзор',
  },
  clients: {
    id: 'clients',
    hash: '#clients',
    label: 'Клиенты',
  },
  'business-context': {
    id: 'business-context',
    hash: '#business-context',
    label: 'Контекст бизнеса',
  },
  integrations: {
    id: 'integrations',
    hash: '#integrations',
    label: 'Интеграции',
  },
  ai: {
    id: 'ai',
    hash: '#ai',
    label: 'AI-аналитик',
  },
  wordstat: {
    id: 'wordstat',
    hash: '#wordstat',
    label: 'Wordstat',
    mode: 'module',
  },
  optimization: {
    id: 'optimization',
    hash: '#optimization',
    label: 'Оптимизация',
  },
  journal: {
    id: 'journal',
    hash: '#journal',
    label: 'Журнал',
    mode: 'module',
  },
});

export const DEFAULT_ROUTE_ID = APP_ROUTES.dashboard.id;

export const LEGACY_ROUTE_REDIRECTS = Object.freeze({
  audit: 'ai',
  recommendations: 'ai',
  reports: 'dashboard',
  autopilot: 'optimization',
  context: 'business-context',
  memory: 'business-context',
  'ai-models': 'ai',
  models: 'ai',
});

export const APP_ROUTE_IDS = Object.freeze(Object.keys(APP_ROUTES));

export function isKnownRoute(routeId) {
  return APP_ROUTE_IDS.includes(routeId);
}

export function normalizeRouteId(routeId) {
  if (typeof routeId !== 'string') {
    return DEFAULT_ROUTE_ID;
  }

  const cleanedRouteId = routeId.replace(/^#/, '').trim();
  return isKnownRoute(cleanedRouteId) ? cleanedRouteId : DEFAULT_ROUTE_ID;
}

export function normalizeAppRouteId(routeId) {
  if (typeof routeId !== 'string') {
    return DEFAULT_ROUTE_ID;
  }

  const cleanedRouteId = routeId.replace(/^#/, '').trim();
  if (isKnownRoute(cleanedRouteId)) return cleanedRouteId;
  return LEGACY_ROUTE_REDIRECTS[cleanedRouteId] || DEFAULT_ROUTE_ID;
}

export function routeToHash(routeId) {
  return APP_ROUTES[normalizeRouteId(routeId)].hash;
}

export function getRouteMode(routeId) {
  return APP_ROUTES[normalizeAppRouteId(routeId)]?.mode || 'module';
}

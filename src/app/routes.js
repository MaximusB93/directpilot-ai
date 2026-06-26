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
  },
});

export const DEFAULT_ROUTE_ID = APP_ROUTES.dashboard.id;

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

export function routeToHash(routeId) {
  return APP_ROUTES[normalizeRouteId(routeId)].hash;
}

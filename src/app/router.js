import { DEFAULT_ROUTE_ID, normalizeRouteId, routeToHash } from './routes.js';

export function currentHashRoute() {
  return normalizeRouteId(window.location.hash || DEFAULT_ROUTE_ID);
}

export function navigateToRoute(routeId, { replace = false } = {}) {
  const normalizedRouteId = normalizeRouteId(routeId);
  const nextHash = routeToHash(normalizedRouteId);

  if (window.location.hash === nextHash) {
    return normalizedRouteId;
  }

  if (replace) {
    const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;
    window.history.replaceState(null, '', nextUrl);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    return normalizedRouteId;
  }

  window.location.hash = nextHash;
  return normalizedRouteId;
}

export function ensureRouteHash() {
  const routeId = currentHashRoute();

  if (!window.location.hash) {
    return navigateToRoute(routeId, { replace: true });
  }

  return routeId;
}

export function onRouteChange(callback) {
  const handleRouteChange = () => {
    callback(currentHashRoute());
  };

  window.addEventListener('hashchange', handleRouteChange);
  return () => window.removeEventListener('hashchange', handleRouteChange);
}

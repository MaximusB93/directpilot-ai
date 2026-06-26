import { DEFAULT_ROUTE_ID, normalizeRouteId } from './routes.js';

const APP_STATE_EVENT = 'directpilot:state-change';
const CLIENT_CHANGED_EVENT = 'directpilot:client-change';
const ROUTE_CHANGED_EVENT = 'directpilot:route-change';

const state = {
  routeId: DEFAULT_ROUTE_ID,
  selectedClientId: '',
  clients: [],
  user: null,
  isLoading: false,
};

function emitStateChange(type, detail) {
  window.dispatchEvent(new CustomEvent(APP_STATE_EVENT, {
    detail: {
      type,
      state: getAppState(),
      ...detail,
    },
  }));
}

export function getAppState() {
  return {
    ...state,
    clients: [...state.clients],
  };
}

export function setRouteId(routeId) {
  const normalizedRouteId = normalizeRouteId(routeId);

  if (state.routeId === normalizedRouteId) {
    return getAppState();
  }

  state.routeId = normalizedRouteId;
  emitStateChange('route', { routeId: normalizedRouteId });
  window.dispatchEvent(new CustomEvent(ROUTE_CHANGED_EVENT, {
    detail: { routeId: normalizedRouteId },
  }));

  return getAppState();
}

export function setSelectedClientId(clientId) {
  const nextClientId = typeof clientId === 'string' ? clientId : '';

  if (state.selectedClientId === nextClientId) {
    return getAppState();
  }

  state.selectedClientId = nextClientId;
  emitStateChange('client', { clientId: nextClientId });
  window.dispatchEvent(new CustomEvent(CLIENT_CHANGED_EVENT, {
    detail: { clientId: nextClientId },
  }));

  return getAppState();
}

export function setClients(clients) {
  state.clients = Array.isArray(clients) ? [...clients] : [];
  emitStateChange('clients', { clients: [...state.clients] });
  return getAppState();
}

export function setUser(user) {
  state.user = user || null;
  emitStateChange('user', { user: state.user });
  return getAppState();
}

export function setIsLoading(isLoading) {
  state.isLoading = Boolean(isLoading);
  emitStateChange('loading', { isLoading: state.isLoading });
  return getAppState();
}

export function onAppStateChange(callback) {
  const handleStateChange = (event) => callback(event.detail);
  window.addEventListener(APP_STATE_EVENT, handleStateChange);
  return () => window.removeEventListener(APP_STATE_EVENT, handleStateChange);
}

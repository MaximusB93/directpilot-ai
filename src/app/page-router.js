import { normalizeRouteId } from './routes.js';
import { getPageByRouteId, getPageContract } from '../pages/index.js';

export function resolveAppPage(routeId) {
  const normalizedRouteId = normalizeRouteId(routeId);
  const page = getPageByRouteId(normalizedRouteId);
  const contract = getPageContract(normalizedRouteId);

  return {
    routeId: normalizedRouteId,
    page,
    contract,
    isRegistered: Boolean(page),
    isLegacy: !page,
    legacyRenderer: contract?.legacyRenderer || null,
  };
}

export function routeHasPageModule(routeId) {
  return resolveAppPage(routeId).isRegistered;
}

export function routeUsesLegacyRenderer(routeId) {
  return resolveAppPage(routeId).isLegacy;
}

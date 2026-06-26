import { normalizeRouteId } from './routes.js';
import {
  getPageByRouteId,
  getPageContract,
  getPageContentRenderer,
  getPageRenderer,
} from '../pages/index.js';

export function resolveAppPage(routeId) {
  const normalizedRouteId = normalizeRouteId(routeId);
  const page = getPageByRouteId(normalizedRouteId);
  const contract = getPageContract(normalizedRouteId);
  const renderer = getPageRenderer(normalizedRouteId);
  const contentRenderer = getPageContentRenderer(normalizedRouteId);

  return {
    routeId: normalizedRouteId,
    page,
    contract,
    renderer,
    contentRenderer,
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

export function resolvePageRenderer(routeId) {
  return resolveAppPage(routeId).renderer;
}

export function resolvePageContentRenderer(routeId) {
  return resolveAppPage(routeId).contentRenderer;
}

import { resolveAppPage } from './page-router.js';
import { currentHashRoute, navigateToRoute } from './router.js';
import { normalizeRouteId } from './routes.js';
import { setRouteId } from './state.js';

const LEGACY_VIEW_PARAM = 'view';
const ROUTE_LINK_SELECTOR = '[data-view], [data-go-view]';

function currentViewParam() {
  return new URLSearchParams(window.location.search).get(LEGACY_VIEW_PARAM) || '';
}

function viewParamToRouteId(view) {
  return normalizeRouteId(view);
}

function routeIdToLegacyView(routeId) {
  return normalizeRouteId(routeId);
}

function markRouteResolution(routeId) {
  const resolvedPage = resolveAppPage(routeId);
  document.body.dataset.routeId = resolvedPage.routeId;
  document.body.dataset.routeMode = resolvedPage.isRegistered ? 'module' : 'legacy';
  document.body.dataset.pageModule = resolvedPage.page?.id || '';
}

function replaceLegacyViewParam(routeId) {
  const url = new URL(window.location.href);
  url.searchParams.set(LEGACY_VIEW_PARAM, routeIdToLegacyView(routeId));
  url.hash = routeId ? `#${routeId}` : '';
  window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
}

function navigateLegacyAppToRoute(routeId) {
  const normalizedRouteId = normalizeRouteId(routeId);
  const url = new URL(window.location.href);
  url.searchParams.set(LEGACY_VIEW_PARAM, routeIdToLegacyView(normalizedRouteId));
  url.hash = `#${normalizedRouteId}`;
  window.location.href = `${url.pathname}${url.search}${url.hash}`;
}

function initialRouteId() {
  if (window.location.hash) {
    return currentHashRoute();
  }

  return viewParamToRouteId(currentViewParam());
}

function syncInitialRoute() {
  const routeId = initialRouteId();
  setRouteId(routeId);
  markRouteResolution(routeId);
  replaceLegacyViewParam(routeId);
}

function bindRouteClicks() {
  document.addEventListener('click', (event) => {
    const routeLink = event.target.closest?.(ROUTE_LINK_SELECTOR);
    if (!routeLink || routeLink.closest?.('[data-page="landing"]')) {
      return;
    }

    const routeId = normalizeRouteId(routeLink.dataset.view || routeLink.dataset.goView || '');
    setRouteId(routeId);
    markRouteResolution(routeId);
    navigateToRoute(routeId);
    replaceLegacyViewParam(routeId);
  }, true);
}

function bindHashChanges() {
  window.addEventListener('hashchange', () => {
    const routeId = currentHashRoute();
    setRouteId(routeId);
    markRouteResolution(routeId);

    if (currentViewParam() !== routeIdToLegacyView(routeId)) {
      navigateLegacyAppToRoute(routeId);
    }
  });
}

if (document.body.dataset.page === 'app') {
  syncInitialRoute();
  bindRouteClicks();
  bindHashChanges();
}

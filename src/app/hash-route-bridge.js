import { resolveAppPage } from './page-router.js';
import { currentHashRoute } from './router.js';
import { normalizeRouteId } from './routes.js';
import { setRouteId } from './state.js';

const LEGACY_VIEW_PARAM = 'view';
const ROUTE_LINK_SELECTOR = 'button[data-view], a[data-view], button[data-go-view], a[data-go-view], [role="button"][data-view], [role="button"][data-go-view]';

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
  url.hash = '';
  window.history.replaceState(null, '', `${url.pathname}${url.search}`);
}

function navigateLegacyAppToRoute(routeId) {
  const normalizedRouteId = normalizeRouteId(routeId);
  const url = new URL(window.location.href);
  url.searchParams.set(LEGACY_VIEW_PARAM, routeIdToLegacyView(normalizedRouteId));
  url.hash = '';
  window.location.href = `${url.pathname}${url.search}`;
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
    const editableTarget = event.target.closest?.('input, textarea, select, [contenteditable="true"]');
    const editableLabel = event.target.closest?.('label')?.querySelector?.('input, textarea, select, [contenteditable="true"]');
    if (editableTarget || editableLabel) {
      event.stopPropagation();
      return;
    }
    const routeLink = event.target.closest?.(ROUTE_LINK_SELECTOR);
    if (!routeLink || routeLink.closest?.('[data-page="landing"]')) {
      return;
    }

    const routeId = normalizeRouteId(routeLink.dataset.view || routeLink.dataset.goView || '');
    setRouteId(routeId);
    markRouteResolution(routeId);
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

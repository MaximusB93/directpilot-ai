import {
  DASHBOARD_PAGE_ID,
  dashboardPage,
  dashboardPageContract,
  renderDashboardContent,
  renderDashboardPage,
} from './dashboard.js';

export const APP_PAGES = {
  [DASHBOARD_PAGE_ID]: dashboardPage,
};

export const PAGE_CONTRACTS = {
  [DASHBOARD_PAGE_ID]: dashboardPageContract(),
};

export const PAGE_RENDERERS = {
  [DASHBOARD_PAGE_ID]: renderDashboardPage,
};

export const PAGE_CONTENT_RENDERERS = {
  [DASHBOARD_PAGE_ID]: renderDashboardContent,
};

export function getPageByRouteId(routeId) {
  return APP_PAGES[routeId] || null;
}

export function getPageContract(routeId) {
  return PAGE_CONTRACTS[routeId] || null;
}

export function getPageRenderer(routeId) {
  return PAGE_RENDERERS[routeId] || null;
}

export function getPageContentRenderer(routeId) {
  return PAGE_CONTENT_RENDERERS[routeId] || null;
}

export function listRegisteredPages() {
  return Object.values(APP_PAGES);
}

import { DASHBOARD_PAGE_ID, dashboardPage, dashboardPageContract } from './dashboard.js';

export const APP_PAGES = {
  [DASHBOARD_PAGE_ID]: dashboardPage,
};

export const PAGE_CONTRACTS = {
  [DASHBOARD_PAGE_ID]: dashboardPageContract(),
};

export function getPageByRouteId(routeId) {
  return APP_PAGES[routeId] || null;
}

export function getPageContract(routeId) {
  return PAGE_CONTRACTS[routeId] || null;
}

export function listRegisteredPages() {
  return Object.values(APP_PAGES);
}

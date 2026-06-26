export const DASHBOARD_PAGE_ID = 'dashboard';

export const dashboardPage = Object.freeze({
  id: DASHBOARD_PAGE_ID,
  title: 'Обзор',
  description: 'Операционный центр клиента: готовность данных, синхронизация, диагностика и быстрые действия.',
});

export function canRenderDashboardPage(routeId) {
  return routeId === DASHBOARD_PAGE_ID;
}

export function dashboardPageContract() {
  return {
    routeId: DASHBOARD_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'clients',
      'syncJobs',
      'performanceSummary',
      'businessContext',
      'yandexIntegration',
    ],
    legacyRenderer: 'renderDashboard',
    extractionStatus: 'contract-only',
    nextStep: 'Move renderDashboard markup from src/main.js after routing is stable.',
  };
}

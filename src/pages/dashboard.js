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
    extractionStatus: 'adapter-ready',
    nextStep: 'Wire src/main.js dashboard route to renderDashboardPage, then move markup in smaller slices.',
  };
}

export function renderDashboardPage({ legacyRenderDashboard } = {}) {
  if (typeof legacyRenderDashboard !== 'function') {
    throw new Error('renderDashboardPage requires legacyRenderDashboard while dashboard markup still lives in src/main.js');
  }

  return legacyRenderDashboard();
}

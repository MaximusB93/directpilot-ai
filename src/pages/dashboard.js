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
    extractionStatus: 'content-composer-ready',
    extractedBuilders: [
      'renderDashboardIntro',
      'renderDashboardNextStepPanel',
      'renderDashboardEmptyClientPanel',
      'renderDashboardConnectedPanels',
      'renderDashboardContent',
    ],
    nextStep: 'Wire src/main.js renderDashboard to renderDashboardContent in one controlled patch.',
  };
}

export function renderDashboardIntro({ clientName, hasClient, escapeHtml }) {
  return `
    <div class="pageIntro">
      <span class="eyebrow">📊 Обзор</span>
      <h2>${hasClient ? escapeHtml(clientName) : 'Подготовьте первого клиента к анализу'}</h2>
      <p>${hasClient ? 'Здесь видно, что уже готово, что мешает синхронизации и какой следующий шаг даст максимум пользы.' : 'Создайте клиента, чтобы подключить данные, запустить синхронизацию и открыть AI-анализ.'}</p>
    </div>
  `;
}

export function renderDashboardNextStepPanel({
  nextAction,
  readyCount,
  readinessLength,
  hasClient,
  hasPerformanceData,
  candidateNegativeKeywords,
  syncLoading,
  canRunSync,
  nextTarget,
  syncStatusMessage,
  renderActionButton,
  formatNumberSafe,
  badgeClassForStatus,
  compactStatusLabel,
  escapeHtml,
}) {
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Следующий шаг</h3>
          <p>${escapeHtml(nextAction.description || nextAction.label || '')}</p>
        </div>
        <span class="aiStatusBadge ${badgeClassForStatus(nextAction.status)}">${escapeHtml(compactStatusLabel(nextAction.status))}</span>
      </div>
      <div class="authStatus integrationStatus"><strong>${escapeHtml(nextAction.nextAction)}</strong></div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Готовность</span><strong>${formatNumberSafe(readyCount)} / ${formatNumberSafe(readinessLength)}</strong></article>
        <article class="kpi blue"><span>Клиент</span><strong>${hasClient ? 'Готово' : 'Нужно действие'}</strong></article>
        <article class="kpi orange"><span>Данные</span><strong>${hasPerformanceData ? 'Готово' : 'Нет данных'}</strong></article>
        <article class="kpi orange"><span>Кандидаты в минус-слова</span><strong>${formatNumberSafe(candidateNegativeKeywords || 0)}</strong></article>
      </div>
      <div class="heroActions">
        ${renderActionButton('Клиенты', 'data-go-view="clients"')}
        ${renderActionButton('Контекст бизнеса', 'data-go-view="business-context"')}
        ${renderActionButton('Интеграции', 'data-go-view="integrations"')}
        ${renderActionButton(syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию', `data-sync-client ${canRunSync && !syncLoading ? '' : 'disabled'}`, 'primary')}
        ${renderActionButton('Перейти к шагу', `data-go-view="${escapeHtml(nextTarget)}"`, 'primary')}
      </div>
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
    </section>
  `;
}

export function renderDashboardEmptyClientPanel() {
  return `
    <section class="panel emptyStatePanel">
      <h3>Нет клиента</h3>
      <p>Создайте клиента, чтобы подключить данные и запустить анализ. После этого DirectPilot покажет готовность, синхронизацию, сводку и AI-план.</p>
      <button class="approveButton" data-view="clients">Перейти к клиентам</button>
    </section>
  `;
}

export function renderDashboardConnectedPanels({
  renderSyncCenter,
  renderBusinessContextPanel,
  renderSyncDiagnosticsPanel,
  renderYesterdaySummaryPanel,
  renderYandexDirectAuditPanel,
  renderPerformanceSummaryPanel,
}) {
  return `
    ${renderSyncCenter()}
    ${renderBusinessContextPanel(true)}
    ${renderSyncDiagnosticsPanel(true)}
    ${renderYesterdaySummaryPanel()}
    ${renderYandexDirectAuditPanel(true)}
    ${renderPerformanceSummaryPanel()}
  `;
}

export function renderDashboardContent(context) {
  const {
    hasClient,
    readiness,
    nextAction,
    renderReadinessPanel,
  } = context;

  return `
    ${renderDashboardIntro(context)}
    ${renderDashboardNextStepPanel(context)}
    ${renderReadinessPanel(readiness, nextAction)}
    ${hasClient ? renderDashboardConnectedPanels(context) : renderDashboardEmptyClientPanel(context)}
  `;
}

export function renderDashboardPage({ legacyRenderDashboard } = {}) {
  if (typeof legacyRenderDashboard !== 'function') {
    throw new Error('renderDashboardPage requires legacyRenderDashboard while dashboard markup still lives in src/main.js');
  }

  return legacyRenderDashboard();
}

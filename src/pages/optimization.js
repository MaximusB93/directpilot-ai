export const OPTIMIZATION_PAGE_ID = 'optimization';

export const optimizationPage = {
  id: OPTIMIZATION_PAGE_ID,
  title: 'Оптимизация',
  description: 'Диагностика, план оптимизации, черновики действий, согласование и безопасный предпросмотр.',
};

export function optimizationPageContract() {
  return {
    routeId: OPTIMIZATION_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
      'performanceSummary',
      'optimizationPlan',
      'optimizationActions',
      'optimizationFilter',
      'optimizationActionFilter',
      'optimizationExecutionPreviews',
    ],
    legacyRenderer: 'renderOptimization',
    extractionStatus: 'content-composer-ready',
    extractedBuilders: [
      'renderOptimizationIntro',
      'renderOptimizationPlanPanel',
      'renderOptimizationActionsPanel',
      'renderOptimizationContent',
    ],
    nextStep: 'Move AI assistant page last after optimization wiring is stable.',
  };
}

export function renderOptimizationIntro({ escapeHtml }) {
  return `
    <div class="pageIntro">
      <span class="eyebrow">Оптимизация</span>
      <h2>Диагностика → план → согласование</h2>
      <p>${escapeHtml('DirectPilot формирует черновики действий и безопасный предпросмотр. Изменения в Яндекс.Директ здесь не применяются.')}</p>
    </div>
  `;
}

function renderPreviewList(title, items = [], escapeHtml) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) return '';
  return `
    <div class="previewList">
      <strong>${escapeHtml(title)}</strong>
      <ul>${list.map((item) => `<li>${escapeHtml(String(item))}</li>`).join('')}</ul>
    </div>
  `;
}

function renderExecutionPreview(previewData, escapeHtml) {
  if (!previewData) return '';
  return `
    <div class="executionPreviewCard">
      <div class="authStatus integrationStatus">Это только предпросмотр. Изменения в Яндекс.Директ не применяются.</div>
      <div class="insightGrid">
        <article><span>Статус</span><strong>${escapeHtml(previewData.status || 'черновик')}</strong></article>
        <article><span>Можно применить</span><strong>Нет</strong></article>
        <article><span>Тип действия</span><strong>${escapeHtml(previewData.action_type || 'manual_review')}</strong></article>
      </div>
      ${previewData.summary ? `<p>${escapeHtml(previewData.summary)}</p>` : ''}
      ${renderPreviewList('Что будет подготовлено', previewData.would_do, escapeHtml)}
      ${renderPreviewList('Какие данные нужны', previewData.required_data, escapeHtml)}
      ${renderPreviewList('Чего не хватает', previewData.missing_data, escapeHtml)}
      ${renderPreviewList('Проверки безопасности', previewData.safety_checks, escapeHtml)}
      ${renderPreviewList('Предупреждения', previewData.warnings, escapeHtml)}
      ${previewData.next_step ? `<div class="authStatus integrationStatus"><strong>Следующий шаг:</strong> ${escapeHtml(previewData.next_step)}</div>` : ''}
    </div>
  `;
}

export function renderOptimizationPlanPanel({
  selectedClientId,
  optimizationPlan = null,
  optimizationPlanLoading = false,
  optimizationActionsLoading = false,
  optimizationStatus = '',
  normalizeDate,
  formatNumberSafe,
  formatPercent,
  formatMoney,
  escapeHtml,
}) {
  const plan = optimizationPlan;

  return `
    <section class="panel optimizationPlanPanel">
      <div class="panelHeader">
        <div><h3>1. План действий</h3><p>Правила и AI формируют черновики на основе кампаний, CPA по целям и поисковых запросов.</p></div>
        <div class="heroActions">
          <button class="secondaryButton" data-load-optimization-plan ${selectedClientId && !optimizationPlanLoading ? '' : 'disabled'}>${optimizationPlanLoading ? 'Формируем...' : 'Обновить план'}</button>
          <button class="approveButton" data-create-optimization-drafts ${selectedClientId && plan && !optimizationActionsLoading ? '' : 'disabled'}>Сохранить как черновики</button>
        </div>
      </div>
      ${optimizationStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationStatus)}</div>` : ''}
      ${plan ? `
        <div class="optimizationGrid">
          <article><span>Сгенерировано</span><strong>${normalizeDate(plan.generatedAt)}</strong></article>
          <article><span>Рекомендации бюджета</span><strong>${formatNumberSafe(plan.dailyBudgetRecommendations.length)}</strong></article>
          <article><span>Корректировки устройств</span><strong>${formatNumberSafe(plan.deviceAdjustments.length)}</strong></article>
        </div>
        <div class="recommendationGrid">
          ${plan.dailyBudgetRecommendations.slice(0, 6).map((item) => `<article><div class="confidence">${formatPercent((item.confidence || 0) * 100)}</div><h3>${escapeHtml(item.campaign_name || item.campaignName || 'Кампания')}</h3><p>Бюджет: ${formatMoney(item.current_budget || item.currentBudget || 0)} → ${formatMoney(item.recommended_budget || item.recommendedBudget || 0)}</p><small>${escapeHtml(item.reason || '')}</small></article>`).join('')}
          ${plan.deviceAdjustments.slice(0, 6).map((item) => `<article><div class="confidence">${formatPercent((item.confidence || 0) * 100)}</div><h3>${escapeHtml(item.device || 'Устройство')}</h3><p>Корректировка: ${item.current_modifier ?? item.currentModifier ?? 0}% → ${item.recommended_modifier ?? item.recommendedModifier ?? 0}%</p><small>${escapeHtml(item.reason || '')}</small></article>`).join('')}
        </div>
      ` : '<div class="authStatus integrationStatus">План пока не сформирован. Загрузите статистику и нажмите «Обновить план».</div>'}
    </section>
  `;
}

export function renderOptimizationActionsPanel({
  selectedClientId,
  optimizationActionFilter = 'all',
  optimizationActionsLoading = false,
  optimizationActionsStatus = '',
  optimizationExecutionPreviews = {},
  getFilteredOptimizationActions,
  compactStatusLabel,
  escapeHtml,
}) {
  const actions = getFilteredOptimizationActions();
  const statusCounts = actions.reduce((acc, action) => {
    const status = action.status || 'draft';
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});

  return `
    <section class="panel optimizationActionsPanel">
      <div class="panelHeader">
        <div><h3>2. Согласование</h3><p>Черновики можно просмотреть, одобрить или отклонить. Одобрение не применяет изменения в Директе.</p></div>
        <div class="heroActions">
          <select data-optimization-action-filter>
            <option value="all" ${optimizationActionFilter === 'all' ? 'selected' : ''}>Все</option>
            <option value="draft" ${optimizationActionFilter === 'draft' ? 'selected' : ''}>Черновики</option>
            <option value="approved" ${optimizationActionFilter === 'approved' ? 'selected' : ''}>Одобрено</option>
            <option value="rejected" ${optimizationActionFilter === 'rejected' ? 'selected' : ''}>Отклонено</option>
          </select>
          <button class="secondaryButton" data-load-optimization-actions ${selectedClientId && !optimizationActionsLoading ? '' : 'disabled'}>${optimizationActionsLoading ? 'Загрузка...' : 'Обновить'}</button>
        </div>
      </div>
      <div class="insightGrid">
        <article><span>Черновики</span><strong>${statusCounts.draft || 0}</strong></article>
        <article><span>Одобрено</span><strong>${statusCounts.approved || 0}</strong></article>
        <article><span>Отклонено</span><strong>${statusCounts.rejected || 0}</strong></article>
        <article><span>К предпросмотру</span><strong>${(statusCounts.approved || 0) + (statusCounts.reviewed || 0)}</strong></article>
      </div>
      ${optimizationActionsStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationActionsStatus)}</div>` : ''}
      ${actions.length ? `<div class="actionList">${actions.map((action) => {
        const preview = optimizationExecutionPreviews[action.id];
        return `<article class="optimizationAction ${action.status || 'draft'}"><div><span>${escapeHtml(compactStatusLabel(action.status || 'draft'))}</span><h3>${escapeHtml(action.title || action.entityName || action.actionType || 'Действие')}</h3><p>${escapeHtml(action.description || action.reason || '')}</p><small>${escapeHtml(action.entityType || '')} · ${escapeHtml(action.actionType || '')}</small></div><div class="actionButtons"><button class="secondaryButton" data-preview-optimization-action="${escapeHtml(action.id)}">Предпросмотр</button><button class="approveButton" data-update-optimization-action="${escapeHtml(action.id)}" data-status="approved">Одобрить</button><button class="dangerButton" data-update-optimization-action="${escapeHtml(action.id)}" data-status="rejected">Отклонить</button></div>${preview?.loading ? '<div class="authStatus integrationStatus">Загружаем предпросмотр...</div>' : ''}${preview?.error ? `<div class="authStatus integrationStatus">${escapeHtml(preview.error)}</div>` : ''}${preview?.data ? `<details class="quietDetails executionPreviewDetails" open><summary>3. Предпросмотр применения</summary>${renderExecutionPreview(preview.data, escapeHtml)}</details>` : ''}</article>`;
      }).join('')}</div>` : '<div class="authStatus integrationStatus">Черновиков пока нет. Сформируйте план и нажмите «Сохранить как черновики».</div>'}
    </section>
  `;
}

export function renderOptimizationContent(context) {
  return `
    ${renderOptimizationIntro(context)}
    ${renderOptimizationPlanPanel(context)}
    ${renderOptimizationActionsPanel(context)}
  `;
}

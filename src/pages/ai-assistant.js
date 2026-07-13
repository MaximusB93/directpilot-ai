export const AI_ASSISTANT_PAGE_ID = 'ai';

export const aiAssistantPage = {
  id: AI_ASSISTANT_PAGE_ID,
  title: 'AI-аналитик',
  description: 'Единый AI workspace: чат, методика анализа, модель, рекомендации и память проекта.',
};

export function aiAssistantPageContract() {
  return {
    routeId: AI_ASSISTANT_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
      'aiStatus',
      'aiModelSettings',
      'aiChatMessages',
      'aiChatInput',
      'aiChatLoading',
      'aiChatError',
      'clientAiRecommendations',
      'performanceSummary',
      'businessContext',
      'optimizationActions',
    ],
    legacyRenderer: 'renderAiAssistant',
    extractionStatus: 'content-composer-ready',
    extractedBuilders: [
      'renderAiAssistantIntro',
      'renderAiStatusPanel',
      'renderAiPromptDebugPanel',
      'renderAiChat',
      'renderClientAiRecommendations',
      'renderAiQuickActions',
      'renderAiAssistantContent',
    ],
    nextStep: 'Split AI state and event handlers after the page content composer is stable.',
  };
}

export function renderAiAssistantIntro({ escapeHtml }) {
  return '';
}

export function renderAiMethodologyPanel() {
  return `
    <section class="panel aiMethodPanel">
      <div class="panelHeader">
        <div><h3>Как DirectPilot анализирует РК</h3><p>Методика идёт от контекста бизнеса к данным и безопасным черновикам действий.</p></div>
      </div>
      <ol class="methodologyList">
        <li>Контекст бизнеса: ниша, офферы, география, ограничения.</li>
        <li>Качество данных: цели, синхронизация, доступность конверсий по целям.</li>
        <li>Кампании: расход, CTR, CPA по целям, конверсии и критичные отклонения.</li>
        <li>Поисковые запросы: интент, нерелевантность, минус-слова и риски.</li>
        <li>План действий: только черновики, без применения в Яндекс.Директ.</li>
      </ol>
    </section>
  `;
}

export function renderAiStatusPanel({
  aiStatus = {},
  selectedAiModel = '',
  selectedAiPreset = 'balanced',
  aiResolvedMaxTokens = 900,
  escapeHtml,
}) {
  const models = aiStatus.models || [];
  const selectedModel = models.find((model) => model.id === selectedAiModel);
  const resolvedModel = selectedModel?.name || selectedModel?.label || selectedAiModel || 'Qwen3 14B · Баланс';
  const presetLabel = {
    economy: 'Эконом',
    balanced: 'Баланс',
    deep: 'Максимум',
    advanced: 'Максимум',
  }[selectedAiPreset] || selectedAiPreset;

  return `
    <section class="panel aiStatusPanel">
      <div class="panelHeader">
        <div><h3>Модель AI</h3><p>Настройки модели вынесены в отдельный раздел, чтобы чат оставался рабочей областью аналитика.</p></div>
        <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'Готов' : 'Нет ключа'}</span>
      </div>
      <div class="aiModelSummary">
        <article><span>Модель</span><strong>${escapeHtml(resolvedModel)}</strong></article>
        <article><span>Профиль</span><strong>${escapeHtml(presetLabel)}</strong></article>
        <article><span>Лимит ответа</span><strong>${escapeHtml(String(aiResolvedMaxTokens))} токенов</strong></article>
      </div>
      <button class="secondaryButton" type="button" data-view="settings">Открыть настройки</button>
      ${aiStatus.configured ? '' : `<div class="authStatus integrationStatus">${escapeHtml(aiStatus.message || 'OpenRouter не настроен.')}</div>`}
    </section>
  `;
}

export function renderAiPromptDebugPanel({
  selectedClientId,
  aiPromptDebugLoading = false,
  aiPromptDebugError = '',
  aiPromptDebug = null,
  formatNumberSafe,
  escapeHtml,
}) {
  return `
    <section class="panel aiPromptPanel">
      <details class="quietDetails">
        <summary>Диагностика размера AI-контекста</summary>
        <div class="panelHeader">
          <div><h3>Проверка контекста</h3><p>Показывает, поместится ли текущий чат и данные клиента в выбранную модель.</p></div>
          <button class="secondaryButton" data-ai-prompt-debug ${selectedClientId && !aiPromptDebugLoading ? '' : 'disabled'}>${aiPromptDebugLoading ? 'Проверяем...' : 'Проверить контекст'}</button>
        </div>
        ${aiPromptDebugError ? `<div class="authStatus integrationStatus">${escapeHtml(aiPromptDebugError)}</div>` : ''}
        ${aiPromptDebug ? `
          <div class="insightGrid">
            <article><span>Оценка токенов</span><strong>${formatNumberSafe(aiPromptDebug.estimated_tokens || 0)}</strong></article>
            <article><span>Лимит</span><strong>${formatNumberSafe(aiPromptDebug.target_context_tokens || 0)}</strong></article>
            <article><span>Инструменты</span><strong>${formatNumberSafe(aiPromptDebug.tool_calls || 0)}</strong></article>
          </div>
          <details class="quietDetails"><summary>Безопасный preview prompt</summary><pre class="promptPreview">${escapeHtml(aiPromptDebug.prompt_preview || '')}</pre></details>
        ` : '<div class="authStatus integrationStatus">Пока нет данных. Нажмите «Проверить контекст».</div>'}
      </details>
    </section>
  `;
}

export function renderAiChat({
  campaignOptions = [],
  aiChatSelectedCampaignName = '',
  aiChatMessages = [],
  aiChatInput = '',
  aiChatLoading = false,
  aiChatError = '',
  aiChatErrorDetails = null,
  aiChatToolTraces = [],
  escapeHtml,
}) {
  return `
    <section class="panel aiChatPanel">
      <div class="panelHeader">
        <div><h3>AI-чат</h3><p>Задавайте вопросы по Директу, целям, бизнес-контексту, поисковым запросам и черновикам действий.</p></div>
        <span class="aiStatusBadge ${aiChatLoading ? 'pending' : 'ready'}">${aiChatLoading ? 'Думает' : 'Готов'}</span>
      </div>
      <div class="aiChatToolbar">
        <label>Кампания
          <select data-ai-chat-campaign>
            <option value="">Все кампании</option>
            ${campaignOptions.map((name) => `<option value="${escapeHtml(name)}" ${aiChatSelectedCampaignName === name ? 'selected' : ''}>${escapeHtml(name)}</option>`).join('')}
          </select>
        </label>
        <button class="secondaryButton" data-ai-audit-start="full_account">Аудит</button>
        <button class="secondaryButton" data-ai-chat-sample="Разбери вчерашний день по кампаниям и конверсиям по целям.">Вчера</button>
        <button class="secondaryButton" data-ai-chat-sample="Проанализируй поисковые запросы и предложи минус-слова с рисками.">Запросы</button>
      </div>
      <div class="aiChatMessages" data-ai-chat-messages>
        ${aiChatMessages.map((message) => `<article class="aiChatMessage ${message.role}"><span>${message.role === 'user' ? 'Вы' : 'AI'}</span>${message.role === 'user' ? `<p>${escapeHtml(message.content)}</p>` : renderSafeMarkdown(message.content)}</article>`).join('')}
      </div>
      ${aiChatError ? `<div class="authStatus integrationStatus">${escapeHtml(aiChatError)}${aiChatErrorDetails?.retry_suggestion ? `<br>${escapeHtml(aiChatErrorDetails.retry_suggestion)}` : ''}</div>` : ''}
      <form class="aiChatForm" data-ai-chat-form>
        <textarea name="message" placeholder="Например: почему CPA вырос и какие кампании проверить?">${escapeHtml(aiChatInput)}</textarea>
        <button class="approveButton" type="submit" ${aiChatLoading ? 'disabled' : ''}>${aiChatLoading ? 'Отправляем...' : 'Спросить AI'}</button>
      </form>
      ${aiChatToolTraces.length ? `
        <details class="toolTraceDetails"><summary>Использованные инструменты</summary>
          <div class="toolTraceList">${aiChatToolTraces.map((trace) => `<article><strong>${escapeHtml(trace.tool || 'tool')}</strong><pre>${escapeHtml(JSON.stringify(trace, null, 2))}</pre></article>`).join('')}</div>
        </details>
      ` : ''}
    </section>
  `;
}

export function renderAiAuditJob({
  selectedClientId,
  aiAuditJob = null,
  aiAuditLoading = false,
  aiAuditError = '',
  escapeHtml,
}) {
  const stages = [
    ['collect_context', 'Данные клиента'],
    ['classify_campaigns', 'Классификация кампаний'],
    ['create_investigation_plan', 'План проверок'],
    ['validate_data_requests', 'Проверка запросов'],
    ['collect_drilldowns', 'Дополнительные данные'],
    ['verify_hypotheses', 'Проверка гипотез'],
    ['generate_answer', 'Формирование результата'],
    ['finalize', 'Готово'],
  ];
  const foundStageIndex = stages.findIndex(([id]) => id === aiAuditJob?.current_stage);
  const stageIndex = foundStageIndex < 0 ? 0 : foundStageIndex;
  const terminal = ['completed', 'failed', 'cancelled'].includes(aiAuditJob?.status);
  const stageStartedMs = Date.parse(aiAuditJob?.stage_started_at || '');
  const stageElapsedSeconds = Number.isFinite(stageStartedMs)
    ? Math.max(0, Math.floor((Date.now() - stageStartedMs) / 1000))
    : 0;
  const stageRunsLong = aiAuditJob?.status === 'generating' && stageElapsedSeconds > 90;
  const statusLabel = {
    queued: 'В очереди',
    collecting_context: 'Собираем данные',
    context_ready: 'Контекст готов',
    generating: aiAuditJob?.current_stage === 'generate_answer' ? 'AI формирует результат' : 'AI анализирует',
    completed: 'Готово',
    failed: 'Ошибка',
    cancelled: 'Отменено',
  }[aiAuditJob?.status] || 'Не запущен';
  const investigation = aiAuditJob?.context_metadata?.investigation || {};
  const requestedDimensions = investigation.requestedDimensions || [];
  const runtime = aiAuditJob?.context_metadata?.runtime || {};
  const tokenUsage = runtime.tokenUsage || {};
  const helperWarnings = (aiAuditJob?.context_metadata?.warnings || [])
    .filter((item) => item?.code === 'planner_fallback_used' || item?.code === 'verification_fallback_used');
  return `
    <section class="panel aiAuditJobPanel">
      <div class="panelHeader">
        <div><h3>Аудит аккаунта</h3><p>Полный аудит выполняется по этапам и сохраняется в проекте. Можно обновить страницу без потери задачи.</p></div>
        <span class="aiStatusBadge ${aiAuditJob?.status === 'completed' ? 'ready' : 'pending'}">${escapeHtml(statusLabel)}</span>
      </div>
      ${aiAuditJob ? `
        <div class="aiAuditProgress"><span style="width:${Math.max(0, Math.min(100, Number(aiAuditJob.progress_percent) || 0))}%"></span></div>
        <strong>Прогресс: ${escapeHtml(String(aiAuditJob.progress_percent || 0))}%</strong>
        ${aiAuditJob.status === 'generating' ? `<p class="aiAuditStageRuntime">Этап выполняется ${escapeHtml(String(stageElapsedSeconds))} сек. · попытка ${escapeHtml(String(aiAuditJob.stage_attempt || 1))}${stageRunsLong ? ' · <strong>Этап выполняется дольше обычного</strong>' : ''}</p>` : ''}
        <ol class="aiAuditStages">
          ${stages.map(([, label], index) => `<li class="${index < stageIndex || aiAuditJob.status === 'completed' ? 'done' : index === stageIndex && !terminal ? 'active' : ''}">${index < stageIndex || aiAuditJob.status === 'completed' ? '✓' : index === stageIndex && !terminal ? '•' : '○'} ${escapeHtml(label)}</li>`).join('')}
        </ol>
        ${requestedDimensions.length ? `<div class="aiAuditInvestigation"><strong>AI запросил дополнительные данные:</strong> ${requestedDimensions.map((value) => escapeHtml({ ad_groups: 'группы', search_queries: 'поисковые запросы', goals: 'цели', placements: 'площадки', audiences: 'аудитории', retargeting_segments: 'сегменты ретаргетинга', devices: 'устройства', geo: 'география', demographics: 'демография', frequency: 'частота', lead_quality: 'качество лидов' }[value] || value)).join(', ')}.<small>Раунд ${escapeHtml(String(runtime.investigationRound || 1))} из 2 · запросов ${escapeHtml(String(runtime.requestsCount || 0))} · служебных AI-вызовов ${escapeHtml(String(runtime.helperProviderCallsCount || 0))} · финальных ${escapeHtml(String(runtime.finalProviderCallsCount || 0))}</small></div>` : ''}
        ${helperWarnings.length && !aiAuditJob.result ? `<aside class="aiAuditNotice"><strong>Аудит продолжен безопасно.</strong>${helperWarnings.map((item) => `<p>${escapeHtml(item.message || '')}</p>`).join('')}</aside>` : ''}
        ${runtime.requestsCount ? `<div class="aiAuditDataSources"><span><strong>Saved data requests:</strong> ${escapeHtml(String(runtime.savedDataRequestsCount || 0))}</span><span><strong>Live Direct API calls:</strong> ${escapeHtml(String(runtime.directApiCallsCount || 0))}</span>${Number(runtime.directApiCallsCount || 0) === 0 ? '<small>Дополнительные данные получены из последней синхронизации DirectPilot.</small>' : ''}</div>` : ''}
        ${aiAuditJob.status === 'completed' && tokenUsage.total ? `<div class="aiAuditUsage"><span>Prompt tokens: ${escapeHtml(String(tokenUsage.prompt || 0))}</span><span>Completion tokens: ${escapeHtml(String(tokenUsage.completion || 0))}</span><span>Total tokens: ${escapeHtml(String(tokenUsage.total || 0))}</span></div>` : ''}
        ${aiAuditJob.error_message ? `<div class="authStatus integrationStatus">${escapeHtml(aiAuditJob.error_message)}</div>` : ''}
        ${aiAuditJob.answer || aiAuditJob.result ? `<div><h4>Результат аудита</h4>${renderAiAuditResult(aiAuditJob.result, aiAuditJob.answer, escapeHtml, aiAuditJob)}</div>` : ''}
        <div class="heroActions">
          ${!terminal ? '<button class="secondaryButton" data-ai-audit-cancel>Отменить</button>' : ''}
          ${aiAuditJob.status === 'failed' && aiAuditJob.retryable ? '<button class="approveButton" data-ai-audit-retry>Повторить этап</button>' : ''}
          ${aiAuditJob.status === 'failed' ? '<button class="secondaryButton" data-ai-audit-reset>Завершить и начать новый аудит</button>' : ''}
          ${aiAuditJob.result?.truncated ? '<button class="approveButton" data-ai-audit-compact-retry>Повторить в более компактном формате</button>' : ''}
          ${['completed', 'cancelled'].includes(aiAuditJob.status) ? '<button class="secondaryButton" data-ai-audit-new>Новый аудит</button>' : ''}
        </div>
      ` : `<button class="approveButton" data-ai-audit-start="full_account" ${selectedClientId && !aiAuditLoading ? '' : 'disabled'}>${aiAuditLoading ? 'Создаём...' : 'Запустить полный аудит'}</button>`}
      ${aiAuditError ? `<div class="authStatus integrationStatus">${escapeHtml(aiAuditError)}</div>` : ''}
    </section>
  `;
}


export function renderClientAiRecommendations({
  selectedClientId,
  aiRecommendationsLoading = false,
  aiRecommendationsError = '',
  clientAiRecommendations = null,
  escapeHtml,
}) {
  return `
    <section class="panel aiRecommendationsPanel">
      <details class="quietDetails">
        <summary>AI-план и рекомендации</summary>
        <div class="panelHeader"><div><h3>AI-рекомендации по клиенту</h3><p>Генерируются с учётом синхронизации, бизнес-контекста и настроек токенов.</p></div><button class="approveButton" data-client-ai-recommendations ${selectedClientId && !aiRecommendationsLoading ? '' : 'disabled'}>${aiRecommendationsLoading ? 'Генерируем...' : 'Сформировать'}</button></div>
        ${aiRecommendationsError ? `<div class="authStatus integrationStatus">${escapeHtml(aiRecommendationsError)}</div>` : ''}
        ${clientAiRecommendations?.recommendations?.length ? `
          <div class="aiDraftGrid">
            ${clientAiRecommendations.recommendations.map((item) => `<article><span>${escapeHtml(item.priority || 'medium')}</span><h3>${escapeHtml(item.title || 'Рекомендация')}</h3><p>${escapeHtml(item.description || item.reason || '')}</p><small>${escapeHtml(item.expected_effect || item.effort || '')}</small></article>`).join('')}
          </div>
        ` : '<div class="authStatus integrationStatus">AI-рекомендаций пока нет.</div>'}
      </details>
    </section>
  `;
}

export function renderAiQuickActions({
  aiLoading = false,
  aiError = '',
  aiResult = null,
  escapeHtml,
}) {
  return `
    <section class="panel aiQuickActions"><h3>Быстрые действия AI</h3><div class="heroActions">
      <button class="secondaryButton" data-ai-audit-start="full_account" ${aiLoading ? 'disabled' : ''}>Аудит по чеклисту</button>
      <button class="secondaryButton" data-ai-audit-start="critical_issues" ${aiLoading ? 'disabled' : ''}>Критичные проблемы</button>
      <button class="secondaryButton" data-ai-prompt="search_queries" ${aiLoading ? 'disabled' : ''}>Поисковые запросы</button>
      <button class="secondaryButton" data-ai-prompt="quick_wins" ${aiLoading ? 'disabled' : ''}>Quick wins</button>
      <button class="secondaryButton" data-ai-prompt="yesterday" ${aiLoading ? 'disabled' : ''}>Вчерашний день</button>
    </div>${aiError ? `<div class="authStatus integrationStatus">${escapeHtml(aiError)}</div>` : ''}${aiResult ? `<pre class="aiResult">${escapeHtml(aiResult.text || aiResult.answer || JSON.stringify(aiResult, null, 2))}</pre>` : ''}</section>
  `;
}

export function renderAiAssistantContent(context) {
  return `
    ${renderAiAssistantIntro(context)}
    ${renderAiMethodologyPanel(context)}
    ${renderAiStatusPanel(context)}
    ${renderAiAuditJob(context)}
    ${renderAiQuickActions(context)}
    ${renderAiChat(context)}
  `;
}
import { renderSafeMarkdown } from '../core/markdown.js';

function auditCoverageLabel(key) {
  return {
    account: 'Аккаунт', campaigns: 'Кампании', adGroups: 'Группы', keywords: 'Ключи',
    searchQueries: 'Запросы', placements: 'Площадки', audiences: 'Аудитории',
    adsAndCreatives: 'Объявления и креативы', demographics: 'Демография', devices: 'Устройства',
    geo: 'География', goals: 'Цели', crmLeadQuality: 'CRM и качество лидов',
  }[key] || key;
}

function formatAuditDate(value) {
  if (!value) return '—';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return year && month && day ? `${day}.${month}.${year}` : String(value);
}

function renderFinding(item, escapeHtml) {
  return `<article class="aiAuditFinding">
    <div class="panelHeader"><div><span>${escapeHtml(item.campaign_name || 'Аккаунт')}</span><h4>${escapeHtml(item.problem || 'Проблема')}</h4></div><span class="aiStatusBadge ${item.risk === 'high' ? 'pending' : 'ready'}">Риск: ${escapeHtml(item.risk || 'не указан')}</span></div>
    <p><strong>Факт:</strong> ${escapeHtml(item.fact || '—')}</p>
    ${item.evidence?.length ? `<details><summary>Доказательства</summary><ul>${item.evidence.map((value) => `<li>${escapeHtml(value)}</li>`).join('')}</ul></details>` : ''}
    ${item.hypothesis ? `<p><strong>Гипотеза:</strong> ${escapeHtml(item.hypothesis)}</p>` : ''}
    <p><strong>Рекомендация:</strong> ${escapeHtml(item.recommendation || '—')}</p>
    <small>Тип: ${escapeHtml(item.campaign_type || 'unknown')} · Уровень: ${escapeHtml(item.analysis_level || 'campaign')} · Проверка: ${escapeHtml(item.verification_status || 'unverified')} · Уверенность: ${escapeHtml(item.confidence || 'low')} · Требуется подтверждение: ${item.requires_human_approval === false ? 'нет' : 'да'}</small>
  </article>`;
}

export function renderAiAuditResult(result, fallbackAnswer, escapeHtml, job = {}) {
  const structured = result?.structured;
  const period = structured?.meta?.period || result?.analysisPeriod || job.context_metadata?.analysisPeriod || {};
  const coverage = structured?.meta?.data_coverage || result?.dataCoverage || job.context_metadata?.dataCoverage || {};
  const periodLine = `Период анализа: ${formatAuditDate(period.date_from || period.dateFrom)}–${formatAuditDate(period.date_to || period.dateTo)}, ${escapeHtml(String(period.days || '—'))} дней.`;
  if (!structured) {
    return `<div class="aiAuditResult"><p class="aiAuditPeriod">${periodLine}</p>${result?.warnings?.map((warning) => `<div class="authStatus integrationStatus">${escapeHtml(warning)}</div>`).join('') || ''}${renderSafeMarkdown(result?.fallbackMarkdown || fallbackAnswer || '')}</div>`;
  }
  const coverageRows = Object.entries(coverage).map(([key, item]) => `<tr><th>${escapeHtml(auditCoverageLabel(key))}</th><td><span class="aiStatusBadge ${item.available ? 'ready' : 'pending'}">${item.available ? 'Доступно' : 'Не собрано'}</span></td><td>${escapeHtml(String(item.analyzed || 0))}${item.total === null || item.total === undefined ? '' : ` / ${escapeHtml(String(item.total))}`}</td><td>${escapeHtml(item.reason || item.source || '—')}</td></tr>`).join('');
  return `<div class="aiAuditResult">
    <p class="aiAuditPeriod">${periodLine}</p>
    <div class="aiAuditMeta"><span>Сравнение: ${formatAuditDate(period.comparison_date_from)}–${formatAuditDate(period.comparison_date_to)}</span><span>Модель: ${escapeHtml(structured.meta?.model || job.returned_model || job.model || '—')}</span><span>Лимит: ${escapeHtml(String(structured.meta?.output_budget_tokens || job.max_tokens || '—'))} токенов</span><span>Полнота: ${escapeHtml(result?.completeness || 'structured')}</span><span>Качество данных: ${escapeHtml(structured.data_quality?.status || 'partial')}</span><span>Время: ${escapeHtml(String(job.timings?.totalElapsedMs || '—'))} мс</span></div>
    ${result?.warnings?.filter((warning) => !String(warning).includes('достиг лимита')).map((warning) => `<div class="authStatus integrationStatus">${escapeHtml(warning)}</div>`).join('') || ''}
    ${result?.truncated ? '<div class="authStatus integrationStatus"><strong>Ответ модели достиг лимита и мог быть обрезан.</strong></div>' : ''}
    <section><h4>Итог</h4><p>${escapeHtml(structured.executive_summary || '')}</p></section>
    <details open><summary>Что проанализировано</summary><div class="markdownTableWrap"><table><thead><tr><th>Уровень</th><th>Статус</th><th>Проанализировано</th><th>Источник / причина</th></tr></thead><tbody>${coverageRows}</tbody></table></div></details>
    ${structured.critical_findings?.length ? `<section><h4>Критические проблемы</h4><div class="aiAuditFindingGrid">${structured.critical_findings.map((item) => renderFinding(item, escapeHtml)).join('')}</div></section>` : ''}
    ${structured.opportunities?.length ? `<section><h4>Возможности</h4><div class="aiAuditFindingGrid">${structured.opportunities.map((item) => renderFinding(item, escapeHtml)).join('')}</div></section>` : ''}
    ${structured.action_plan?.length ? `<section><h4>План действий</h4><ol>${[...structured.action_plan].sort((a, b) => Number(a.priority) - Number(b.priority)).map((item) => `<li><strong>${escapeHtml(item.action)}</strong> — ${escapeHtml(item.reason)} <small>Объект: ${escapeHtml(item.scope)} · ${escapeHtml(item.mode)} · подтверждение обязательно</small></li>`).join('')}</ol></section>` : ''}
    ${structured.prohibited_actions?.length ? `<aside class="aiAuditNotice"><h4>Запрещённые автоматические действия</h4><ul>${structured.prohibited_actions.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul></aside>` : ''}
    <aside class="aiAuditNotice"><h4>Ограничения</h4><ul>${(structured.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>Не указаны.</li>'}</ul></aside>
    <section><h4>Вывод</h4><p>${escapeHtml(structured.conclusion || '')}</p></section>
  </div>`;
}

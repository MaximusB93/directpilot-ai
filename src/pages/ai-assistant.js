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
        ${aiChatMessages.map((message) => `<article class="aiChatMessage ${message.role}"><span>${message.role === 'user' ? 'Вы' : 'AI'}</span>${message.role === 'user' ? `<p>${escapeHtml(message.content)}</p>` : `${renderAiAssistantMarkdown(message.content)}${message.auditJobId ? '<button class="secondaryButton" data-ai-audit-open>Открыть полный аудит</button>' : ''}`}</article>`).join('')}
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

function auditRequestStatusLabel(status) {
  return ({
    pending: 'Ожидает выполнения', queued: 'Ожидает выполнения', processing: 'Формируется отчёт',
    ready: 'Данные получены', completed: 'Данные получены',
    collected: 'Данные получены', cached: 'Получено из кеша', partial: 'Получены частично',
    insufficient_data: 'Недостаточно данных', unavailable: 'Источник недоступен',
    unsupported: 'Не поддерживается', failed: 'Ошибка получения', not_applicable: 'Неприменимо',
    rejected_by_validation: 'Отклонено backend-валидатором',
  })[status] || 'Ожидает';
}

function auditVerificationStatusLabel(status) {
  return ({
    confirmed: 'Подтверждена', partially_confirmed: 'Подтверждена частично', rejected: 'Отклонена',
    unverified: 'Не подтверждена', not_applicable: 'Неприменима', collecting_data: 'Собираем данные',
    proposed: 'Предложена',
  })[status] || 'Проверяется';
}

function auditSourceLabel(source) {
  return ({
    live: 'Live Яндекс.Директ', cached_live: 'Кеш live-данных', saved: 'Сохранённые данные',
    mixed: 'Смешанный источник',
    yandex_direct_live_report: 'Live-отчёт Директа', yandex_direct_live_service: 'Live API Директа',
    yandex_direct_cached_live: 'Кеш live-отчёта', direct_read_cache: 'Кеш DirectPilot',
    saved_campaign_stats: 'Сохранённая статистика', unavailable: 'Источник недоступен',
  })[source] || (source ? 'Доверенный read-only источник' : 'Ожидается');
}

function auditCapabilityLabel(value) {
  return ({
    campaigns: 'кампании', campaign_performance: 'эффективность кампаний', goals: 'цели',
    search_queries: 'поисковые запросы', ad_groups: 'группы', ad_group_performance: 'эффективность групп',
    keywords: 'ключевые фразы', keyword_performance: 'эффективность ключей', placements: 'площадки',
    devices: 'устройства', geo: 'география', retargeting_lists: 'списки ретаргетинга',
    retargeting_segments: 'сегменты ретаргетинга', audience_targets: 'аудиторные таргетинги',
  })[value] || value || 'данные';
}

function renderAuditRequestTrace(metadata, escapeHtml) {
  const trace = metadata?.publicRequestTrace || [];
  if (!trace.length) return '';
  const shown = trace.slice(0, 20);
  const overflow = trace.slice(20);
  const options = (key) => [...new Set(trace.map((item) => item[key]).filter(Boolean))];
  const renderRows = (items) => items.map((item) => `<tr data-audit-trace-row data-campaign="${escapeHtml(item.campaignName || '')}" data-round="${escapeHtml(String(item.roundNumber || ''))}" data-hypothesis="${escapeHtml(item.hypothesisType || '')}" data-capability="${escapeHtml(item.capabilityId || '')}" data-status="${escapeHtml(item.status || '')}" data-source="${escapeHtml(item.source || '')}">
    <td>${escapeHtml(String(item.roundNumber || 1))}</td><td>${escapeHtml(item.campaignName || 'Аккаунт')}</td><td>${escapeHtml(item.hypothesisType || '—')}</td>
    <td>${escapeHtml(auditCapabilityLabel(item.capabilityId))}</td><td>${escapeHtml(item.reason || '—')}</td><td>${escapeHtml(auditSourceLabel(item.source))}</td>
    <td>${escapeHtml(auditRequestStatusLabel(item.status))}</td>
    <td>${escapeHtml(String(item.rowsReceived || 0))}</td><td>${escapeHtml(String(item.rowsAnalyzedByBackend || 0))}</td><td>${escapeHtml(String(item.rowsSentToAi || 0))}</td>
    <td>${escapeHtml(String(item.pagination?.pagesCompleted || 0))}</td><td>${item.timing?.elapsedMs == null ? '—' : `${escapeHtml(String(item.timing.elapsedMs))} мс`}</td>
    <td><details><summary>Подробнее</summary>
      <p><b>Ожидаемая польза:</b> ${escapeHtml(item.expectedInformationGain || '—')}</p>
      <p><b>Период:</b> ${escapeHtml(item.period?.dateFrom || '—')} — ${escapeHtml(item.period?.dateTo || '—')}</p>
      <p><b>Метрики:</b> ${(item.semanticMetrics || []).map((value) => escapeHtml(value)).join(', ') || '—'}</p>
      <p><b>Объём:</b> получено ${escapeHtml(String(item.rowsReceived || 0))}, нормализовано ${escapeHtml(String(item.rowsNormalized || 0))}, проверено backend ${escapeHtml(String(item.rowsAnalyzedByBackend || 0))}, передано AI ${escapeHtml(String(item.rowsSentToAi || 0))}.</p>
      <p><b>Lifecycle:</b> ${(item.statusHistory || []).map((event) => escapeHtml(auditRequestStatusLabel(event.status))).join(' → ') || '—'}</p>
      <p><b>Отчёт:</b> страниц ${escapeHtml(String(item.pagination?.pagesCompleted || 0))}; offline ${item.offlineReport?.used ? escapeHtml(auditRequestStatusLabel(item.offlineReport.status)) : 'не использовался'}; кеш ${item.cache?.hit ? 'да' : 'нет'}; fallback ${item.fallback?.used ? 'да' : 'нет'}.</p>
      <p><b>Качество чисел:</b> известно ${escapeHtml(String(item.dataQuality?.numericStateCounts?.known || 0))}, нет данных ${escapeHtml(String(item.dataQuality?.numericStateCounts?.missing || 0))}, некорректно ${escapeHtml(String(item.dataQuality?.numericStateCounts?.invalid || 0))}.</p>
      ${(item.evidence?.confirmationRules || []).length ? `<p><b>Подтверждающие правила:</b> ${(item.evidence.confirmationRules || []).map((rule) => escapeHtml(rule.summary || rule.rule_code || rule.ruleCode || '')).join('; ')}</p>` : ''}
      ${(item.evidence?.rejectionRules || []).length ? `<p><b>Опровергающие правила:</b> ${(item.evidence.rejectionRules || []).map((rule) => escapeHtml(rule.summary || rule.rule_code || rule.ruleCode || '')).join('; ')}</p>` : ''}
      ${(item.evidence?.limitations || []).length ? `<p><b>Ограничения:</b> ${item.evidence.limitations.map((value) => escapeHtml(value)).join('; ')}</p>` : ''}
      <p><b>Проверка:</b> ${escapeHtml(auditVerificationStatusLabel(item.verification?.status))}. ${escapeHtml(item.verification?.summary || '')}</p>
      <p><b>Следующий шаг:</b> ${escapeHtml(item.nextStep?.reason || '—')}</p>
      ${item.safeError?.code ? `<p><b>Ошибка:</b> ${escapeHtml(item.safeError.message || item.safeError.code)}</p>` : ''}
    </details></td>
  </tr>`).join('');
  const table = (items) => `<div class="markdownTableWrap"><table><thead><tr><th>Раунд</th><th>Кампания</th><th>Гипотеза</th><th>Что запросили</th><th>Зачем</th><th>Источник</th><th>Статус</th><th>Получено</th><th>Backend</th><th>AI</th><th>Страницы</th><th>Время</th><th>Результат</th></tr></thead><tbody>${renderRows(items)}</tbody></table></div>`;
  return `
    <details class="quietDetails" open data-audit-trace>
      <summary>Запросы к данным · ${escapeHtml(String(trace.length))}</summary>
      <div class="aiAuditTraceFilters">
        <label>Кампания <select data-audit-trace-filter="campaign"><option value="">Все</option>${options('campaignName').map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('')}</select></label>
        <label>Раунд <select data-audit-trace-filter="round"><option value="">Все</option>${options('roundNumber').map((value) => `<option value="${escapeHtml(String(value))}">${escapeHtml(String(value))}</option>`).join('')}</select></label>
        <label>Гипотеза <select data-audit-trace-filter="hypothesis"><option value="">Все</option>${options('hypothesisType').map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('')}</select></label>
        <label>Срез <select data-audit-trace-filter="capability"><option value="">Все</option>${options('capabilityId').map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(auditCapabilityLabel(value))}</option>`).join('')}</select></label>
        <label>Статус <select data-audit-trace-filter="status"><option value="">Все</option>${options('status').map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(auditRequestStatusLabel(value))}</option>`).join('')}</select></label>
        <label>Источник <select data-audit-trace-filter="source"><option value="">Все</option>${options('source').map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(auditSourceLabel(value))}</option>`).join('')}</select></label>
      </div>
      ${table(shown)}
      ${overflow.length ? `<details class="quietDetails"><summary>Показать ещё ${overflow.length}</summary>${table(overflow)}</details>` : ''}
    </details>
  `;
}

function renderAuditTechnicalDiagnostics(metadata, runtime, escapeHtml, result = null) {
  const diagnostics = metadata?.requestDiagnostics || {};
  const statuses = diagnostics.statusCounts || {};
  const quality = metadata?.dataQualitySummary?.numericStateCounts || {};
  const baseline = metadata?.baselineEvidenceSummary || [];
  const baselineRows = baseline.reduce((sum, item) => sum + Number(item.rowsReceived || 0), 0);
  const baselineAnalyzed = baseline.reduce((sum, item) => sum + Number(item.rowsAnalyzed || 0), 0);
  const baselineSent = baseline.reduce((sum, item) => sum + Number(item.rowsSentToAi || 0), 0);
  const modelParsing = result?.modelResponseParsing || null;
  const finalTokenUsage = result?.finalTokenUsage || null;
  const validationPaths = (modelParsing?.validationErrorPaths || []).slice(0, 20);
  const finalStatusLabel = {
    prepared: 'финальная проекция подготовлена',
    compact_retry_pending: 'компактный повтор ожидает запуска',
    compact_retry_prepared: 'компактная проекция подготовлена',
    calling_provider: 'формируется финальный AI-отчёт',
    calling_provider_compact: 'формируется компактный AI-отчёт',
    provider_response_received: 'ответ AI-провайдера получен',
    validating_schema: 'проверяется структура AI-отчёта',
    provider_response_truncated: 'ответ AI-провайдера обрезан по лимиту',
    provider_context_limit_rejected: 'провайдер отклонил размер контекста',
    retrying_after_provider_context_rejection: 'повторяем с более компактным контекстом',
    provider_completed: 'AI-отчёт сформирован',
    backend_fallback: 'сохранён безопасный backend-результат',
    backend_fallback_missing_mandatory_evidence: 'аудит завершён с неполным покрытием обязательных данных',
    backend_fallback_after_provider_context_rejection: 'сохранён backend-результат после отказа провайдера',
    backend_fallback_after_provider_timeout: 'сохранён backend-результат после таймаута финальной модели',
    backend_fallback_after_final_stage_stale: 'сохранён backend-результат после восстановления финального этапа',
    backend_fallback_after_json_parse: 'ответ модели не удалось разобрать; показан безопасный backend-отчёт',
    backend_fallback_after_schema_validation: 'ответ модели не прошёл структурный контракт; показан безопасный backend-отчёт',
  }[runtime.finalGenerationStatus] || 'финальная генерация ещё не началась';
  const reconciliation = result?.finalOutputEvidenceReconciliation
    || result?.structuredParsing?.evidenceReconciliation
    || null;
  const reconciliationLabel = reconciliation?.status === 'final_output_evidence_reconciled'
    ? 'Финальный ответ согласован с фактически собранными данными'
    : reconciliation?.status === 'consistent'
      ? 'Противоречий с собранными данными не найдено'
      : 'Проверка согласованности ещё не выполнена';
  return `
    <details class="quietDetails">
      <summary>Техническая диагностика аудита</summary>
      <div class="aiAuditRequestCounters">
        <span><strong>${escapeHtml(String(diagnostics.planned || 0))}</strong> запросов</span>
        <span><strong>${escapeHtml(String(statuses.pending || 0))}</strong> ожидают</span>
        <span><strong>${escapeHtml(String(statuses.processing || 0))}</strong> формируются</span>
        <span><strong>${escapeHtml(String(statuses.completed || 0))}</strong> завершены</span>
        <span><strong>${escapeHtml(String(statuses.partial || 0))}</strong> частично</span>
        <span><strong>${escapeHtml(String(statuses.unavailable || 0))}</strong> недоступны</span>
        <span><strong>${escapeHtml(String(statuses.not_applicable || 0))}</strong> неприменимы</span>
        <span><strong>${escapeHtml(String(statuses.failed || 0))}</strong> ошибок</span>
        <span><strong>${escapeHtml(String(diagnostics.cacheHits || 0))}</strong> кеш</span>
        <span><strong>${escapeHtml(String(diagnostics.savedFallbacks || 0))}</strong> fallback</span>
        <span><strong>${escapeHtml(String(diagnostics.offlineReports || 0))}</strong> offline-отчётов</span>
        <span><strong>${escapeHtml(String(diagnostics.pagesLoaded || 0))}</strong> страниц</span>
        <span><strong>${escapeHtml(String(diagnostics.rowsReceived || 0))}</strong> строк получено</span>
        <span><strong>${escapeHtml(String(diagnostics.rowsAnalyzed || 0))}</strong> проверено backend</span>
        <span><strong>${escapeHtml(String(diagnostics.rowsSentToAi || 0))}</strong> передано AI</span>
        <span><strong>${escapeHtml(String(runtime.providerCallsCount || 0))}</strong> AI-вызовов</span>
        <span><strong>${escapeHtml(String(runtime.helperFallbacksCount || 0))}</strong> helper fallback</span>
        <span><strong>${escapeHtml(String(runtime.directApiCallsCount || 0))}</strong> Direct API-вызовов</span>
        <span><strong>${escapeHtml(String(runtime.liveAttempts || 0))}</strong> live-попыток</span>
        <span><strong>${escapeHtml(String(runtime.liveSucceeded || 0))}</strong> live успешно</span>
      </div>
      ${baseline.length ? `<p><b>Fresh baseline:</b> получено ${escapeHtml(String(baselineRows))}, проанализировано backend ${escapeHtml(String(baselineAnalyzed))}, передано AI ${escapeHtml(String(baselineSent))}.</p>` : ''}
      <p>Источники: ${Object.entries(metadata?.dataSourceSummary || {}).map(([source, count]) => `${escapeHtml(auditSourceLabel(source))}: ${escapeHtml(String(count))}`).join(' · ') || 'ожидаются'}.</p>
      <p>Финальная проекция: ${escapeHtml(String(runtime.finalProjectionEstimatedTokens || 0))} токенов. Финальный prompt: ${escapeHtml(String(runtime.finalPromptEstimatedTokens || 0))}. Лимит модели: ${escapeHtml(String(runtime.modelContextLimit || 0))}. Запрошено для ответа: ${escapeHtml(String(runtime.requestedOutputTokens || runtime.reservedOutputTokens || 0))}. Эффективный лимит: ${escapeHtml(String(runtime.effectiveFinalOutputTokens || runtime.reservedOutputTokens || 0))}. Запас безопасности: ${escapeHtml(String(runtime.safetyMarginTokens || 0))}.</p>
      <p>Уровень сжатия: L${escapeHtml(String(runtime.finalCompactionLevel ?? '—'))}. Preflight помещается: ${runtime.preflightFitsModelContext === true ? 'да' : runtime.preflightFitsModelContext === false ? 'нет' : 'ещё не проверено'}. Провайдер отклонил контекст: ${runtime.providerContextRejected ? 'да' : 'нет'}. Backend fallback: ${runtime.backendFallbackUsed ? 'да' : 'нет'}.</p>
      <p>Статус финальной генерации: ${escapeHtml(finalStatusLabel)}${runtime.providerContextErrorCode ? ` · код контекста: ${escapeHtml(String(runtime.providerContextErrorCode))}` : ''}${runtime.providerErrorCode ? ` · код провайдера: ${escapeHtml(String(runtime.providerErrorCode))}` : ''}. Суммарное использование всех AI-вызовов: ${escapeHtml(String(runtime.tokenUsage?.total || 0))} токенов. Время этапов: ${escapeHtml(String(Object.values(runtime.timings || {}).reduce((sum, value) => sum + Number(value || 0), 0)))} мс.</p>
      <p>Согласование evidence: ${escapeHtml(reconciliationLabel)}.</p>
      ${finalTokenUsage ? `<p>Финальный AI-вызов: prompt ${escapeHtml(String(finalTokenUsage.prompt || 0))}, completion ${escapeHtml(String(finalTokenUsage.completion || 0))}, всего ${escapeHtml(String(finalTokenUsage.total || 0))} токенов.</p>` : ''}
      ${result?.backendFallbackUsed ? `<p>Backend fallback: да. Причина: ${escapeHtml(String(result?.structuredParsing?.fallbackReason || modelParsing?.errorCode || 'не указана'))}.${modelParsing ? ` Ошибок структурной проверки: ${escapeHtml(String(modelParsing.validationErrorsCount || 0))}.` : ''}</p>` : ''}
      ${modelParsing ? `<p>Ответ модели: формат ${escapeHtml(String(modelParsing.sourceFormat || 'unknown'))}, результат проверки ${escapeHtml(String(modelParsing.parseOutcome || 'unknown'))}${validationPaths.length ? `, безопасные пути ошибок: ${validationPaths.map((value) => escapeHtml(String(value))).join(', ')}` : ''}. Finish reason: ${escapeHtml(String(result?.finishReason || 'не указан'))}.</p>` : ''}
      <p>Качество числовых данных: известно ${escapeHtml(String(quality.known || 0))}, отсутствует ${escapeHtml(String(quality.missing || 0))}, некорректно ${escapeHtml(String(quality.invalid || 0))}. Причина остановки: ${escapeHtml(metadata?.auditStopReason || 'аудит продолжается')}.</p>
    </details>
  `;
}

function renderAuditInvestigationTree(rounds, escapeHtml) {
  if (!rounds.length) return '';
  return `
    <details class="quietDetails" open>
      <summary>Ход расследования: факты, гипотезы и доказательства</summary>
      <div class="aiAuditInvestigation">
        ${rounds.map((round) => {
          const hypotheses = round.hypotheses || [];
          const requests = round.requests || [];
          const verifications = round.verifications || [];
          const factsById = Object.fromEntries((round.facts || []).map((fact) => [fact.factId, fact]));
          return `
            <section>
              <strong>Раунд ${escapeHtml(String(round.roundNumber || 1))}</strong>
              ${hypotheses.map((hypothesis) => {
                const hypothesisRequests = requests.filter((item) => item.hypothesisId === hypothesis.hypothesisId);
                const verification = verifications.find((item) => item.hypothesis_id === hypothesis.hypothesisId) || {};
                const triggeringFacts = (hypothesis.factIds || []).map((factId) => factsById[factId]).filter(Boolean);
                return `
                <article>
                  <b>${escapeHtml(hypothesis.campaignName || 'Аккаунт')}</b>
                  <p><b>Исходный факт:</b> ${triggeringFacts.length ? triggeringFacts.map((fact) => escapeHtml((fact.evidence || []).join(' ') || fact.metric || '')).join(' ') : 'Доверенный факт не привязан.'}</p>
                  <details class="quietDetails">
                    <summary>Гипотеза: ${escapeHtml(hypothesis.hypothesis || 'Причина проверяется')} · ${escapeHtml(auditVerificationStatusLabel(verification.status || hypothesis.status))}</summary>
                    <p><b>Тип:</b> ${escapeHtml(hypothesis.hypothesisType || '—')}${hypothesis.parentHypothesisId ? ` · <b>Родительская гипотеза:</b> ${escapeHtml(hypothesis.parentHypothesisId)}` : ''}</p>
                    ${hypothesisRequests.length ? `<ul>${hypothesisRequests.map((item) => `<li><b>${escapeHtml(auditCapabilityLabel(item.capabilityId))}</b>: ${escapeHtml(auditRequestStatusLabel(item.status))} · ${escapeHtml(auditSourceLabel(item.source))}${item.rows ? ` · строк: ${escapeHtml(String(item.rows))}` : ''}</li>`).join('')}</ul>` : '<p>Дополнительные запросы не требуются.</p>'}
                    ${(verification.supporting_evidence || []).length ? `<p><b>Подтверждающие данные:</b> ${escapeHtml(verification.supporting_evidence.join(' '))}</p>` : ''}
                    ${(verification.contradicting_evidence || []).length ? `<p><b>Противоречащие данные:</b> ${escapeHtml(verification.contradicting_evidence.join(' '))}</p>` : ''}
                    ${(verification.limitations || []).length ? `<p><b>Ограничения:</b> ${escapeHtml(verification.limitations.join(' '))}</p>` : ''}
                    ${(verification.remaining_data_needed || []).length ? `<p><b>Осталось получить:</b> ${verification.remaining_data_needed.map((value) => escapeHtml(auditCapabilityLabel(value))).join(', ')}</p>` : ''}
                  </details>
                </article>
              `; }).join('')}
              ${round.stopReason ? `<small>Причина остановки раунда: ${escapeHtml(String(round.stopReason))}</small>` : ''}
            </section>
          `;
        }).join('')}
      </div>
    </details>
  `;
}

function renderAuditEvidenceCoverage(job, escapeHtml) {
  const coverage = job?.context_metadata?.evidenceCoverage || job?.result?.evidenceCoverage;
  if (!coverage) return '';
  const summary = coverage.summary || {};
  const state = coverage.completionState || 'legacy_unknown';
  const stateLabels = {
    complete: 'Обязательные данные собраны',
    partial_coverage: 'Аудит завершён с частичным покрытием',
    blocked_missing_evidence: 'Аудит не получил часть обязательных данных',
    legacy_unknown: 'Полнота старого аудита не определена',
  };
  const statusLabels = {
    satisfied: 'Собрано', partial: 'Частично', blocked: 'Заблокировано',
    missing: 'Не собрано', processing: 'Загружается', not_applicable: 'Неприменимо',
  };
  const signalLabels = {
    high_cpa: 'Высокий CPA', spend_without_conversions: 'Расход без конверсий',
    low_data_volume: 'Мало данных', good_campaign_do_not_touch: 'Стабильная кампания',
    tracking_issue_suspected: 'Проверка трекинга', brand_campaign_cannibalization: 'Брендовая каннибализация',
    yan_low_quality_placements: 'Некачественные площадки РСЯ', search_query_waste: 'Нерелевантные запросы',
    budget_spike: 'Скачок расхода', learning_strategy_do_not_touch: 'Обучение стратегии',
  };
  const rows = (coverage.requirements || []).map((item) => `<tr>
    <td>${escapeHtml(item.campaignName || 'Кампания')}</td>
    <td>${escapeHtml(signalLabels[item.signal] || item.signal || 'Сигнал')}</td>
    <td>${escapeHtml(auditDimensionLabel(item.dimension))}</td>
    <td>${escapeHtml(statusLabels[item.status] || item.status || 'Не собрано')}</td>
    <td>${escapeHtml(auditSourceLabel(item.source))}</td>
    <td>${escapeHtml(item.limitations?.[0] || item.reasonCode || '—')}</td>
  </tr>`).join('');
  const isOpen = ['partial_coverage', 'blocked_missing_evidence'].includes(state);
  return `<details class="quietDetails" ${isOpen ? 'open' : ''} data-audit-evidence-coverage>
    <summary>Полнота обязательных данных · ${escapeHtml(stateLabels[state] || state)}</summary>
    <div class="aiAuditRequestCounters">
      <span><strong>${escapeHtml(String(summary.requiredTotal || 0))}</strong> обязательно</span>
      <span><strong>${escapeHtml(String(summary.satisfied || 0))}</strong> собрано</span>
      <span><strong>${escapeHtml(String(summary.partial || 0))}</strong> частично</span>
      <span><strong>${escapeHtml(String(summary.unavailable || 0))}</strong> недоступно</span>
      <span><strong>${escapeHtml(String(summary.notApplicable || 0))}</strong> неприменимо</span>
      <span><strong>${escapeHtml(String(summary.blocked || 0))}</strong> заблокировано</span>
      <span><strong>${escapeHtml(String(summary.missing || 0))}</strong> не собрано</span>
      <span><strong>${escapeHtml(String(summary.processing || 0))}</strong> в обработке</span>
    </div>
    ${state === 'blocked_missing_evidence' ? '<aside class="aiAuditNotice">Полный причинный аудит ограничен: недостающие обязательные данные не заменяются предположениями.</aside>' : ''}
    ${state === 'partial_coverage' ? '<aside class="aiAuditNotice">Часть срезов доступна не полностью. Выводы по ним помечены как ограниченные.</aside>' : ''}
    ${rows ? `<div class="markdownTableWrap"><table><thead><tr><th>Кампания</th><th>Сигнал</th><th>Обязательные данные</th><th>Статус</th><th>Источник</th><th>Причина / ограничение</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p>Для старого аудита детальный реестр не сохранён.</p>'}
  </details>`;
}

function safeAuditJobErrorMessage(job) {
  const message = String(job?.error_message || '').trim();
  if (!message) return '';
  const normalized = message.toLowerCase();
  const internalValidationError = ['validation error for', 'validation errors for', 'errors.pydantic.dev', 'input_value=']
    .some((marker) => normalized.includes(marker));
  if (job?.error_code === 'ai_audit_result_schema_error' || internalValidationError) {
    return 'Не удалось сформировать итоговый структурированный отчёт. Собранные данные сохранены.';
  }
  return message;
}


export function renderAiAuditJob({
  selectedClientId,
  aiAuditJob = null,
  aiAuditLoading = false,
  aiAuditError = '',
  escapeHtml,
}) {
  const stages = [
    ['collect_context', 'Общий анализ'],
    ['classify_campaigns', 'Выбор проблемных кампаний'],
    ['create_investigation_plan', 'Гипотезы'],
    ['validate_data_requests', 'Запрос данных'],
    ['collect_live_data', 'Получение отчётов'],
    ['wait_for_offline_reports', 'Получение отчётов'],
    ['verify_hypotheses', 'Проверка гипотез'],
    ['next_cascade_round', 'Следующий уровень'],
    ['generate_answer', 'Финальный аудит'],
    ['finalize', 'Готово'],
  ];
  const currentStage = aiAuditJob?.current_stage === 'collect_drilldowns' ? 'collect_live_data' : aiAuditJob?.current_stage;
  const foundStageIndex = stages.findIndex(([id]) => id === currentStage);
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
    context_ready: aiAuditJob?.current_stage === 'wait_for_offline_reports'
      ? 'Яндекс.Директ формирует отчёты'
      : aiAuditJob?.current_stage === 'generate_answer' && String(aiAuditJob?.context_metadata?.runtime?.finalGenerationStatus || '').startsWith('compact_retry')
        ? 'Готовим компактный финальный отчёт'
        : 'Контекст готов',
    generating: aiAuditJob?.current_stage === 'generate_answer'
      ? String(aiAuditJob?.context_metadata?.runtime?.finalGenerationStatus || '').includes('compact')
        ? 'AI формирует компактный результат'
        : 'AI формирует результат'
      : 'AI анализирует',
    completed: 'Готово',
    failed: 'Ошибка',
    cancelled: 'Отменено',
  }[aiAuditJob?.status] || 'Не запущен';
  const investigation = aiAuditJob?.context_metadata?.investigation || {};
  const requestedDimensions = investigation.requestedDimensions || [];
  const runtime = aiAuditJob?.context_metadata?.runtime || {};
  const dataRequests = investigation.dataRequests || {};
  const rounds = investigation.rounds || [];
  const publicRounds = aiAuditJob?.context_metadata?.investigationTree || rounds;
  const cachePolicy = aiAuditJob?.context_metadata?.cachePolicy || 'fresh';
  const tokenUsage = runtime.tokenUsage || {};
  const compactGenerationActive = [
    'compact_retry_pending', 'compact_retry_prepared', 'calling_provider_compact',
    'retrying_after_provider_context_rejection',
  ]
    .includes(runtime.finalGenerationStatus);
  const helperWarnings = (aiAuditJob?.context_metadata?.warnings || [])
    .filter((item) => item?.code === 'planner_fallback_used' || item?.code === 'verification_fallback_used');
  const publicErrorMessage = safeAuditJobErrorMessage(aiAuditJob);
  return `
    <section class="panel aiAuditJobPanel" data-ai-audit-panel>
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
        <div class="aiAuditInvestigation"><strong>Данные аудита: ${escapeHtml({ fresh: 'свежие live-данные', prefer_cache: 'кеш с обновлением при необходимости', cache_only: 'только кеш' }[cachePolicy] || cachePolicy)}</strong><small>Раунд ${escapeHtml(String(runtime.investigationRound || 1))} из ${escapeHtml(String(runtime.maxInvestigationRounds || 3))} · запросов ${escapeHtml(String(runtime.requestsCount || 0))} · live-попыток ${escapeHtml(String(dataRequests.liveAttempts || 0))} · успешно ${escapeHtml(String(dataRequests.liveSucceeded || 0))} · кеш ${escapeHtml(String(dataRequests.cacheHits || 0))} · сохранённые данные ${escapeHtml(String(dataRequests.savedFallbacks || 0))} · служебных AI-вызовов ${escapeHtml(String(runtime.helperProviderCallsCount || 0))} · финальных ${escapeHtml(String(runtime.finalProviderCallsCount || 0))}</small></div>
        ${requestedDimensions.length ? `<div class="aiAuditInvestigation"><strong>Запрошены данные:</strong> ${requestedDimensions.map((value) => escapeHtml({ ad_groups: 'группы', search_queries: 'поисковые запросы', goals: 'цели', placements: 'площадки', audiences: 'аудитории', retargeting_segments: 'сегменты ретаргетинга', devices: 'устройства', geo: 'география', demographics: 'демография', frequency: 'частота', lead_quality: 'качество лидов' }[value] || value)).join(', ')}.</div>` : ''}
        ${(dataRequests.live || dataRequests.processing || dataRequests.cacheHits || dataRequests.saved) ? `
          <div class="aiAuditInvestigation">
            <strong>Дополнительные данные</strong>
            <small>Live Direct API: ${escapeHtml(String(dataRequests.live || 0))} · Готово: ${escapeHtml(String(dataRequests.liveCompleted || 0))} · Формируется: ${escapeHtml(String(dataRequests.processing || 0))} · Из кеша: ${escapeHtml(String(dataRequests.cacheHits || 0))} · Saved fallback: ${escapeHtml(String(dataRequests.saved || 0))}</small>
            ${(dataRequests.unavailableCapabilities || []).length ? `<small>Недоступно: ${(dataRequests.unavailableCapabilities || []).map((value) => escapeHtml(value)).join(', ')}.</small>` : ''}
            ${dataRequests.freshestDataAt ? `<small>Свежесть данных: ${escapeHtml(String(dataRequests.freshestDataAt))}.</small>` : ''}
          </div>
        ` : ''}
        ${renderAuditEvidenceCoverage(aiAuditJob, escapeHtml)}
        ${renderAuditInvestigationTree(publicRounds, escapeHtml)}
        ${renderAuditRequestTrace(aiAuditJob.context_metadata || {}, escapeHtml)}
        ${renderAuditTechnicalDiagnostics(aiAuditJob.context_metadata || {}, runtime, escapeHtml, aiAuditJob.result)}
        ${compactGenerationActive ? '<aside class="aiAuditNotice"><strong>Компактная генерация использует уже собранные доказательства.</strong><p>Повторные запросы к Яндекс.Директу не выполняются.</p></aside>' : ''}
        ${helperWarnings.length && !aiAuditJob.result ? `<aside class="aiAuditNotice"><strong>Аудит продолжен безопасно.</strong>${helperWarnings.map((item) => `<p>${escapeHtml(item.message || '')}</p>`).join('')}</aside>` : ''}
        ${aiAuditJob.status === 'completed' && tokenUsage.total ? `<div class="aiAuditUsage"><span>Prompt tokens: ${escapeHtml(String(tokenUsage.prompt || 0))}</span><span>Completion tokens: ${escapeHtml(String(tokenUsage.completion || 0))}</span><span>Total tokens: ${escapeHtml(String(tokenUsage.total || 0))}</span></div>` : ''}
        ${publicErrorMessage ? `<div class="authStatus integrationStatus">${escapeHtml(publicErrorMessage)}</div>` : ''}
        ${aiAuditJob.answer || aiAuditJob.result ? `<div><h4>Результат аудита</h4>${renderAiAuditResult(aiAuditJob.result, aiAuditJob.answer, escapeHtml, aiAuditJob)}</div>` : ''}
        <div class="heroActions">
          ${!terminal ? '<button class="secondaryButton" data-ai-audit-cancel>Отменить</button>' : ''}
          ${aiAuditJob.status === 'failed' && aiAuditJob.retryable ? '<button class="approveButton" data-ai-audit-retry>Повторить этап</button>' : ''}
          ${aiAuditJob.status === 'failed' ? '<button class="secondaryButton" data-ai-audit-reset>Завершить и начать новый аудит</button>' : ''}
          ${(aiAuditJob.result?.truncated || aiAuditJob.result?.compactRetryAvailable) ? '<button class="approveButton" data-ai-audit-compact-retry>Повторить компактную генерацию</button>' : ''}
          ${['completed', 'cancelled'].includes(aiAuditJob.status) ? '<button class="secondaryButton" data-ai-audit-new>Новый аудит</button>' : ''}
        </div>
      ` : `<div class="heroActions"><label>Данные аудита <select data-ai-audit-cache-policy><option value="fresh" selected>Свежие live-данные</option><option value="prefer_cache">Кеш с обновлением</option><option value="cache_only">Только кеш</option></select></label><button class="approveButton" data-ai-audit-start="full_account" ${selectedClientId && !aiAuditLoading ? '' : 'disabled'}>${aiAuditLoading ? 'Создаём...' : 'Запустить полный аудит'}</button></div>`}
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

const RAW_AUDIT_JSON_MESSAGE = 'Структурированный результат скрыт: интерфейс не показывает сырой JSON. Откройте карточку результата аудита или повторите аудит.';

function looksLikeRawStructuredJson(value) {
  const text = String(value || '').trim();
  if (!text) return false;
  if (text.toLowerCase().startsWith('```json')) return true;
  if (text.startsWith('```')) {
    const body = text.replace(/^```[^\n]*\n?/, '').replace(/```\s*$/, '').trim();
    return body.startsWith('{') || body.startsWith('[');
  }
  return text.startsWith('{') || text.startsWith('[');
}

function renderAiAssistantMarkdown(value) {
  return looksLikeRawStructuredJson(value)
    ? `<p class="aiAuditRawJsonNotice">${RAW_AUDIT_JSON_MESSAGE}</p>`
    : renderSafeMarkdown(value);
}

function auditCoverageLabel(key) {
  return {
    account: 'Аккаунт', campaigns: 'Кампании', adGroups: 'Группы', keywords: 'Ключи',
    searchQueries: 'Запросы', placements: 'Площадки', audiences: 'Аудитории',
    adsAndCreatives: 'Объявления и креативы', demographics: 'Демография', devices: 'Устройства',
    geo: 'География', goals: 'Цели', crmLeadQuality: 'CRM и качество лидов',
  }[key] || key;
}

function auditVerificationLabel(status) {
  return {
    confirmed: 'Подтверждено', partially_confirmed: 'Частично подтверждено',
    unverified: 'Не подтверждено', rejected: 'Опровергнуто', not_applicable: 'Неприменимо',
  }[status] || 'Не подтверждено';
}

function auditDimensionLabel(value) {
  return {
    campaign_performance: 'эффективность кампании', conversions_by_goal: 'конверсии по выбранным целям',
    campaign_daily_dynamics: 'дневная динамика кампании', campaign_settings: 'настройки кампании',
    campaign_strategy: 'стратегия кампании', campaign_status: 'статус кампании',
    ad_groups: 'группы', keywords: 'ключевые фразы', search_queries: 'поисковые запросы',
    ad_group_performance: 'эффективность групп', keyword_performance: 'эффективность ключевых фраз',
    autotargeting: 'автотаргетинг', bid_modifiers: 'корректировки ставок',
    ads: 'объявления и креативы', landing_pages: 'посадочные страницы', placements: 'площадки',
    audiences: 'аудитории', retargeting_segments: 'сегменты ретаргетинга',
    audience_exclusions: 'исключения аудиторий', devices: 'устройства', geo: 'география',
    demographics: 'демография', frequency: 'частотность', goals: 'цели',
    conversion_sources: 'источники конверсий', lead_quality: 'качество лидов',
  }[value] || value;
}

function formatAuditDate(value) {
  if (!value) return '—';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return year && month && day ? `${day}.${month}.${year}` : String(value);
}

function renderFinding(item, escapeHtml) {
  const verificationStatus = item.verification_status || 'unverified';
  const verificationClass = verificationStatus === 'confirmed' ? 'ready' : 'pending';
  return `<article class="aiAuditFinding">
    <div class="panelHeader"><div><span>${escapeHtml(item.campaign_name || 'Аккаунт')}</span><h4>${escapeHtml(item.problem || 'Проблема')}</h4></div><div class="aiAuditFindingBadges"><span class="aiStatusBadge ${verificationClass}">${escapeHtml(auditVerificationLabel(verificationStatus))}</span><span class="aiStatusBadge ${item.risk === 'high' ? 'pending' : 'ready'}">Риск: ${escapeHtml(item.risk || 'не указан')}</span></div></div>
    <p><strong>Факт:</strong> ${escapeHtml(item.fact || '—')}</p>
    ${item.evidence?.length ? `<details><summary>Доказательства</summary><ul>${item.evidence.map((value) => `<li>${escapeHtml(value)}</li>`).join('')}</ul></details>` : ''}
    ${item.hypothesis ? `<p><strong>Гипотеза:</strong> ${escapeHtml(item.hypothesis)}</p>` : ''}
    <p><strong>Рекомендация:</strong> ${escapeHtml(item.recommendation || '—')}</p>
    ${item.next_data_needed?.length ? `<p><strong>Недостающие данные:</strong> ${item.next_data_needed.map((value) => escapeHtml(auditDimensionLabel(value))).join(', ')}</p>` : ''}
    <small>Тип: ${escapeHtml(item.campaign_type || 'не определён')} · Уровень: ${escapeHtml(item.analysis_level || 'кампания')} · Уверенность: ${escapeHtml(item.confidence || 'низкая')} · Подтверждение действия: ${item.requires_human_approval === false ? 'не требуется' : 'обязательно'}</small>
  </article>`;
}

function renderFindingSection(title, items, escapeHtml, { open = true } = {}) {
  if (!items.length) return '';
  return `<details class="aiAuditFindingSection" ${open ? 'open' : ''}><summary>${escapeHtml(title)} · ${items.length}</summary><div class="aiAuditFindingGrid">${items.map((item) => renderFinding(item, escapeHtml)).join('')}</div></details>`;
}

function renderAuditDataRequests(job, escapeHtml) {
  const dataRequests = job?.context_metadata?.investigation?.dataRequests || {};
  const statuses = dataRequests.statusCounts || {};
  const planned = Number(dataRequests.planned || 0);
  if (!planned) return '';
  const saved = Number(dataRequests.saved || 0);
  const liveAttempts = Number(dataRequests.liveAttempts ?? dataRequests.live ?? 0);
  const liveSucceeded = Number(dataRequests.liveSucceeded ?? dataRequests.liveCompleted ?? 0);
  const liveProcessing = Number(dataRequests.liveProcessing ?? dataRequests.processing ?? 0);
  const liveFailed = Number(dataRequests.liveFailed || 0);
  const cacheHits = Number(dataRequests.cacheHits || 0);
  const savedFallbacks = Number(dataRequests.savedFallbacks || 0);
  const unavailable = dataRequests.unavailableDimensions || [];
  return `<section class="aiAuditRequestSummary">
    <h4>Дополнительные запросы данных</h4>
    <div class="aiAuditRequestCounters">
      <span><strong>${planned}</strong> запланировано</span>
      <span><strong>${Number(dataRequests.allowed || 0)}</strong> разрешено backend</span>
      <span><strong>${saved}</strong> выполнено по сохранённым данным</span>
      <span><strong>${liveAttempts}</strong> live-попыток</span>
      <span><strong>${liveSucceeded}</strong> live-запросов выполнено</span>
      <span><strong>${liveProcessing}</strong> отчётов готовится</span>
      <span><strong>${liveFailed}</strong> live-ошибок</span>
      <span><strong>${cacheHits}</strong> ответов из кеша</span>
      <span><strong>${savedFallbacks}</strong> переходов к сохранённым данным</span>
      <span><strong>${Number(statuses.unavailable || 0)}</strong> недоступно</span>
      <span><strong>${Number(statuses.not_applicable || 0)}</strong> неприменимо</span>
      <span><strong>${Number(statuses.insufficient_data || 0)}</strong> мало данных</span>
      <span><strong>${Number(statuses.failed || 0)}</strong> ошибок</span>
    </div>
    ${saved && !liveAttempts ? `<p>Выполнено по данным последней синхронизации DirectPilot: ${saved}. Live-запросы к Яндекс.Директу в этом аудите не выполнялись.</p>` : ''}
    ${unavailable.length ? `<aside class="aiAuditNotice"><strong>Не удалось проверить:</strong> ${unavailable.map((value) => escapeHtml(auditDimensionLabel(value))).join(', ')}. Эти данные не учитывались в выводах.</aside>` : ''}
  </section>`;
}

export function renderAiAuditResult(result, fallbackAnswer, escapeHtml, job = {}) {
  const structured = result?.structured;
  const period = structured?.meta?.period || result?.analysisPeriod || job.context_metadata?.analysisPeriod || {};
  const coverage = structured?.meta?.data_coverage || result?.dataCoverage || job.context_metadata?.dataCoverage || {};
  const periodLine = `Период анализа: ${formatAuditDate(period.date_from || period.dateFrom)}–${formatAuditDate(period.date_to || period.dateTo)}, ${escapeHtml(String(period.days || '—'))} дней.`;
  if (!structured) {
    const fallbackValue = result?.fallbackMarkdown || fallbackAnswer || 'AI вернул результат в неподдерживаемом формате.';
    const fallbackMessage = looksLikeRawStructuredJson(fallbackValue)
      ? 'AI вернул результат в неподдерживаемом формате. Метаданные аудита сохранены.'
      : fallbackValue;
    return `<div class="aiAuditResult"><p class="aiAuditPeriod">${periodLine}</p>
      <div class="aiAuditMeta"><span>Модель: ${escapeHtml(job.returned_model || job.model || '—')}</span><span>Время: ${escapeHtml(String(job.timings?.totalElapsedMs || '—'))} мс</span><span>Ошибка формата: ${escapeHtml(result?.structuredParsing?.errorCode || 'json_parse_failed')}</span></div>
      ${result?.warnings?.map((warning) => `<div class="authStatus integrationStatus">${escapeHtml(warning)}</div>`).join('') || ''}
      <div class="aiAuditNotice">${escapeHtml(fallbackMessage)}</div>
      ${renderAuditDataRequests(job, escapeHtml)}
    </div>`;
  }
  const coverageRows = Object.entries(coverage).map(([key, item]) => `<tr><th>${escapeHtml(auditCoverageLabel(key))}</th><td><span class="aiStatusBadge ${item.available ? 'ready' : 'pending'}">${item.available ? 'Доступно' : 'Не собрано'}</span></td><td>${escapeHtml(String(item.analyzed || 0))}${item.total === null || item.total === undefined ? '' : ` / ${escapeHtml(String(item.total))}`}</td><td>${escapeHtml(item.reason || item.source || '—')}</td></tr>`).join('');
  const critical = structured.critical_findings || [];
  const byStatus = (status) => critical.filter((item) => (item.verification_status || 'unverified') === status);
  const opportunities = (structured.opportunities || []).filter((item) => !['rejected', 'not_applicable'].includes(item.verification_status));
  return `<div class="aiAuditResult">
    <p class="aiAuditPeriod">${periodLine}</p>
    <div class="aiAuditMeta"><span>Сравнение: ${formatAuditDate(period.comparison_date_from)}–${formatAuditDate(period.comparison_date_to)}</span><span>Модель: ${escapeHtml(structured.meta?.model || job.returned_model || job.model || '—')}</span><span>Лимит: ${escapeHtml(String(structured.meta?.output_budget_tokens || job.max_tokens || '—'))} токенов</span><span>Полнота: ${escapeHtml(result?.completeness || 'structured')}</span><span>Качество данных: ${escapeHtml(structured.data_quality?.status || 'partial')}</span><span>Время: ${escapeHtml(String(job.timings?.totalElapsedMs || '—'))} мс</span></div>
    ${result?.warnings?.filter((warning) => !String(warning).includes('достиг лимита')).map((warning) => `<div class="authStatus integrationStatus">${escapeHtml(warning)}</div>`).join('') || ''}
    ${result?.truncated ? '<div class="authStatus integrationStatus"><strong>Ответ модели достиг лимита и мог быть обрезан.</strong></div>' : ''}
    <section><h4>Итог</h4><p>${escapeHtml(structured.executive_summary || '')}</p></section>
    <details open><summary>Что проанализировано</summary><div class="markdownTableWrap"><table><thead><tr><th>Уровень</th><th>Статус</th><th>Проанализировано</th><th>Источник / причина</th></tr></thead><tbody>${coverageRows}</tbody></table></div></details>
    ${renderAuditDataRequests(job, escapeHtml)}
    ${renderFindingSection('Подтверждённые проблемы', byStatus('confirmed'), escapeHtml)}
    ${renderFindingSection('Частично подтверждённые проблемы', byStatus('partially_confirmed'), escapeHtml)}
    ${renderFindingSection('Неподтверждённые гипотезы', byStatus('unverified'), escapeHtml)}
    ${renderFindingSection('Опровергнутые гипотезы', byStatus('rejected'), escapeHtml, { open: false })}
    ${opportunities.length ? `<section><h4>Возможности</h4><div class="aiAuditFindingGrid">${opportunities.map((item) => renderFinding(item, escapeHtml)).join('')}</div></section>` : ''}
    ${structured.insufficient_data_campaigns?.length ? `<aside class="aiAuditNotice"><h4>Недостаточно данных</h4><ul>${structured.insufficient_data_campaigns.map((item) => `<li><strong>${escapeHtml(item.campaign_name || 'Кампания')}</strong>: ${escapeHtml(item.reason || 'Недостаточно данных.')} ${item.recommendation ? `<span>${escapeHtml(item.recommendation)}</span>` : ''}${item.next_data_needed?.length ? `<small> Нужны данные: ${item.next_data_needed.map((value) => escapeHtml(auditDimensionLabel(value))).join(', ')}.</small>` : ''}</li>`).join('')}</ul></aside>` : ''}
    ${structured.action_plan?.length ? `<section><h4>План действий</h4><ol>${[...structured.action_plan].sort((a, b) => Number(a.priority) - Number(b.priority)).map((item) => `<li><strong>${escapeHtml(item.action)}</strong> — ${escapeHtml(item.reason)} <small>Объект: ${escapeHtml(item.scope)} · ${escapeHtml(item.mode)} · подтверждение обязательно</small></li>`).join('')}</ol></section>` : ''}
    ${structured.prohibited_actions?.length ? `<aside class="aiAuditNotice"><h4>Запрещённые автоматические действия</h4><ul>${structured.prohibited_actions.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul></aside>` : ''}
    <aside class="aiAuditNotice"><h4>Ограничения</h4><ul>${(structured.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('') || '<li>Не указаны.</li>'}</ul></aside>
    <section><h4>Вывод</h4><p>${escapeHtml(structured.conclusion || '')}</p></section>
  </div>`;
}

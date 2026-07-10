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
        <button class="secondaryButton" data-ai-chat-sample="Проведи аудит Яндекс.Директа по чеклисту и покажи критичные проблемы.">Аудит</button>
        <button class="secondaryButton" data-ai-chat-sample="Разбери вчерашний день по кампаниям и конверсиям по целям.">Вчера</button>
        <button class="secondaryButton" data-ai-chat-sample="Проанализируй поисковые запросы и предложи минус-слова с рисками.">Запросы</button>
      </div>
      <div class="aiChatMessages" data-ai-chat-messages>
        ${aiChatMessages.map((message) => `<article class="aiChatMessage ${message.role}"><span>${message.role === 'user' ? 'Вы' : 'AI'}</span><p>${escapeHtml(message.content)}</p></article>`).join('')}
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
      <button class="secondaryButton" data-ai-prompt="audit" ${aiLoading ? 'disabled' : ''}>Аудит по чеклисту</button>
      <button class="secondaryButton" data-ai-prompt="critical" ${aiLoading ? 'disabled' : ''}>Критичные проблемы</button>
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
    ${renderAiChat(context)}
    ${renderAiQuickActions(context)}
    ${renderAiPromptDebugPanel(context)}
    ${renderClientAiRecommendations(context)}
  `;
}

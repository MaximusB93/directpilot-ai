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
  return `
    <div class="pageIntro">
      <span class="eyebrow">AI-аналитик</span>
      <h2>Один чат для анализа клиента</h2>
      <p>${escapeHtml('AI использует бизнес-контекст, цели, кампании, поисковые запросы, аудит и черновики действий. Настройки модели и диагностика контекста доступны ниже, но основной сценарий — задавать вопросы по выбранному клиенту.')}</p>
    </div>
  `;
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
  selectedAiModel = 'openrouter/auto',
  customAiModel = '',
  customModelValue,
  selectedAiPreset = 'balanced',
  aiResolvedMaxTokens = 900,
  aiMaxTokensMode = 'compact',
  aiToolResultsMode = 'summary',
  aiChatHistoryLimit = 3,
  aiSearchQueryLimit = '',
  aiCompactContext = true,
  escapeHtml,
}) {
  const models = aiStatus.models || [];
  const selectedModelExists = models.some((model) => model.id === selectedAiModel);
  const customActive = selectedAiModel === customModelValue || (!selectedModelExists && selectedAiModel !== 'openrouter/auto');
  const resolvedModel = customActive ? (customAiModel || 'укажите свою модель') : selectedAiModel;
  const presetLabel = {
    economy: 'Эконом',
    balanced: 'Баланс',
    deep: 'Максимум',
    advanced: 'Максимум',
  }[selectedAiPreset] || selectedAiPreset;
  const modelOptions = [
    '<option value="openrouter/auto">openrouter/auto</option>',
    ...models.map((model) => `<option value="${escapeHtml(model.id)}" ${selectedAiModel === model.id ? 'selected' : ''}>${escapeHtml(model.name || model.id)}</option>`),
    `<option value="${customModelValue}" ${customActive ? 'selected' : ''}>Своя модель OpenRouter</option>`,
  ].join('');

  return `
    <section class="panel aiStatusPanel">
      <div class="panelHeader">
        <div><h3>Модель AI</h3><p>${escapeHtml(aiStatus.message || 'Статус OpenRouter неизвестен')}</p></div>
        <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'Готов' : 'Нет ключа'}</span>
      </div>
      <div class="aiModelSummary">
        <article><span>Режим</span><strong>${escapeHtml(presetLabel)}</strong></article>
        <article><span>Фактическая модель</span><strong>${escapeHtml(resolvedModel)}</strong></article>
        <article><span>Лимит ответа</span><strong>${escapeHtml(String(aiResolvedMaxTokens))} токенов</strong></article>
      </div>
      ${customActive ? `<div class="authStatus integrationStatus">Своя/free модель может быть нестабильной: возможны лимиты, 429 и временная недоступность.</div>` : ''}
      <details class="quietDetails">
        <summary>Настройки модели</summary>
        <p class="muted">Режимы DirectPilot влияют на модель по умолчанию, лимит ответа и подробность. OpenRouter получает конкретный ID модели и лимит токенов.</p>
        <div class="aiModelSettings">
          <label>Модель
            <select data-ai-model>${modelOptions}</select>
          </label>
          ${customActive ? `<label>Своя модель
            <input data-ai-custom-model value="${escapeHtml(customAiModel)}" placeholder="openai/gpt-4o" />
          </label>` : '<div class="authStatus integrationStatus">Своя модель не используется, пока не выбран пункт «Своя модель OpenRouter».</div>'}
          <label>Профиль токенов
            <select data-ai-preset>
              <option value="economy" ${selectedAiPreset === 'economy' ? 'selected' : ''}>Эконом · быстрые регулярные проверки</option>
              <option value="balanced" ${selectedAiPreset === 'balanced' ? 'selected' : ''}>Баланс · основной анализ кампаний</option>
              <option value="deep" ${selectedAiPreset === 'deep' ? 'selected' : ''}>Максимум · глубокий разбор</option>
            </select>
          </label>
          <label>AI-context
            <select data-ai-max-tokens-mode>
              <option value="compact" ${aiMaxTokensMode === 'compact' ? 'selected' : ''}>Компактный</option>
              <option value="deep" ${aiMaxTokensMode === 'deep' ? 'selected' : ''}>Расширенный</option>
            </select>
          </label>
          <label>Результаты инструментов
            <select data-ai-tool-results-mode>
              <option value="summary" ${aiToolResultsMode === 'summary' ? 'selected' : ''}>Сводка</option>
              <option value="raw" ${aiToolResultsMode === 'raw' ? 'selected' : ''}>Сырые данные</option>
            </select>
          </label>
          <label>История чата
            <select data-ai-chat-history-limit>
              <option value="1" ${Number(aiChatHistoryLimit) === 1 ? 'selected' : ''}>1 сообщение</option>
              <option value="3" ${Number(aiChatHistoryLimit) === 3 ? 'selected' : ''}>3 сообщения</option>
              <option value="6" ${Number(aiChatHistoryLimit) === 6 ? 'selected' : ''}>6 сообщений</option>
            </select>
          </label>
          <label>Лимит поисковых запросов
            <input data-ai-search-query-limit value="${escapeHtml(aiSearchQueryLimit)}" inputmode="numeric" />
          </label>
          <label class="checkboxLabel"><input type="checkbox" data-ai-compact-context ${aiCompactContext ? 'checked' : ''} /> Сжимать контекст</label>
        </div>
        <p class="muted"><a href="https://openrouter.ai/models" target="_blank" rel="noreferrer">Каталог моделей OpenRouter</a></p>
      </details>
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
      <div class="aiChatMessages">
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
    ${renderAiChat(context)}
    ${renderAiQuickActions(context)}
    ${renderAiStatusPanel(context)}
    ${renderAiPromptDebugPanel(context)}
    ${renderClientAiRecommendations(context)}
  `;
}

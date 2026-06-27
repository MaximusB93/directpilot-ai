export const AI_ASSISTANT_PAGE_ID = 'ai';

export const aiAssistantPage = {
  id: AI_ASSISTANT_PAGE_ID,
  title: 'AI-аналитик',
  description: 'AI workspace: чат, модель OpenRouter, prompt inspector, рекомендации и память проекта.',
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
      <h2>AI workspace для Директа и Метрики</h2>
      <p>${escapeHtml('Настраивайте модель, проверяйте контекст, задавайте вопросы и генерируйте рекомендации по клиенту.')}</p>
    </div>
  `;
}

export function renderAiStatusPanel({
  aiStatus = {},
  selectedAiModel = 'openrouter/auto',
  customAiModel = '',
  customModelValue,
  selectedAiPreset = 'balanced',
  aiMaxTokensMode = 'compact',
  aiToolResultsMode = 'summary',
  aiChatHistoryLimit = 3,
  aiSearchQueryLimit = '',
  aiCompactContext = true,
  escapeHtml,
}) {
  const models = aiStatus.models || [];
  const selectedModelExists = models.some((model) => model.id === selectedAiModel);
  const modelOptions = [
    '<option value="openrouter/auto">openrouter/auto</option>',
    ...models.map((model) => `<option value="${escapeHtml(model.id)}" ${selectedAiModel === model.id ? 'selected' : ''}>${escapeHtml(model.name || model.id)}</option>`),
    `<option value="${customModelValue}" ${selectedAiModel === customModelValue || (!selectedModelExists && selectedAiModel !== 'openrouter/auto') ? 'selected' : ''}>Своя модель OpenRouter</option>`,
  ].join('');

  return `
    <section class="panel aiStatusPanel">
      <div class="panelHeader">
        <div><h3>OpenRouter</h3><p>${escapeHtml(aiStatus.message || 'Статус неизвестен')}</p></div>
        <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'Готов' : 'Нет ключа'}</span>
      </div>
      <div class="aiModelSettings">
        <label>Модель
          <select data-ai-model>${modelOptions}</select>
        </label>
        <label>Своя модель
          <input data-ai-custom-model value="${escapeHtml(customAiModel)}" placeholder="openai/gpt-4o" ${selectedAiModel === customModelValue || !selectedModelExists ? '' : 'disabled'} />
        </label>
        <label>Профиль токенов
          <select data-ai-preset>
            <option value="economy" ${selectedAiPreset === 'economy' ? 'selected' : ''}>Economy · коротко и дёшево</option>
            <option value="balanced" ${selectedAiPreset === 'balanced' ? 'selected' : ''}>Balanced · больше контекста</option>
            <option value="deep" ${selectedAiPreset === 'deep' ? 'selected' : ''}>Deep · максимум деталей</option>
          </select>
        </label>
        <label>AI-context
          <select data-ai-max-tokens-mode>
            <option value="compact" ${aiMaxTokensMode === 'compact' ? 'selected' : ''}>Компактный</option>
            <option value="deep" ${aiMaxTokensMode === 'deep' ? 'selected' : ''}>Расширенный</option>
          </select>
        </label>
        <label>Tool results
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
        <label>Запросов Wordstat / Метрики
          <input data-ai-search-query-limit value="${escapeHtml(aiSearchQueryLimit)}" inputmode="numeric" />
        </label>
        <label class="checkboxLabel"><input type="checkbox" data-ai-compact-context ${aiCompactContext ? 'checked' : ''} /> Сжимать контекст</label>
      </div>
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
      <div class="panelHeader">
        <div><h3>Prompt inspector</h3><p>Проверка размера контекста перед запросом к модели.</p></div>
        <button class="secondaryButton" data-ai-prompt-debug ${selectedClientId && !aiPromptDebugLoading ? '' : 'disabled'}>${aiPromptDebugLoading ? 'Проверяем...' : 'Проверить контекст'}</button>
      </div>
      ${aiPromptDebugError ? `<div class="authStatus integrationStatus">${escapeHtml(aiPromptDebugError)}</div>` : ''}
      ${aiPromptDebug ? `
        <div class="insightGrid">
          <article><span>Оценка токенов</span><strong>${formatNumberSafe(aiPromptDebug.estimated_tokens || 0)}</strong></article>
          <article><span>Лимит</span><strong>${formatNumberSafe(aiPromptDebug.target_context_tokens || 0)}</strong></article>
          <article><span>Tool calls</span><strong>${formatNumberSafe(aiPromptDebug.tool_calls || 0)}</strong></article>
        </div>
        <pre class="promptPreview">${escapeHtml(aiPromptDebug.prompt_preview || '')}</pre>
      ` : '<div class="authStatus integrationStatus">Пока нет данных. Нажмите «Проверить контекст».</div>'}
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
        <div><h3>AI-чат с MCP-инструментами</h3><p>Задавайте вопросы по Директу, Метрике, контексту и оптимизации. AI сам выберет нужные инструменты.</p></div>
        <span class="aiStatusBadge ${aiChatLoading ? 'pending' : 'ready'}">${aiChatLoading ? 'Думает' : 'Готов'}</span>
      </div>
      <div class="aiChatToolbar">
        <label>Кампания
          <select data-ai-chat-campaign>
            <option value="">Все кампании</option>
            ${campaignOptions.map((name) => `<option value="${escapeHtml(name)}" ${aiChatSelectedCampaignName === name ? 'selected' : ''}>${escapeHtml(name)}</option>`).join('')}
          </select>
        </label>
        <button class="secondaryButton" data-ai-chat-sample="Почему вырос CPA за последние 7 дней?">CPA</button>
        <button class="secondaryButton" data-ai-chat-sample="Какие поисковые запросы нужно добавить в минус-слова?">Минус-слова</button>
        <button class="secondaryButton" data-ai-chat-sample="Что в первую очередь проверить в Метрике и целях?">Метрика</button>
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
      <div class="panelHeader"><div><h3>AI-рекомендации по клиенту</h3><p>Генерируются с учётом синхронизации, бизнес-контекста и настроек токенов.</p></div><button class="approveButton" data-client-ai-recommendations ${selectedClientId && !aiRecommendationsLoading ? '' : 'disabled'}>${aiRecommendationsLoading ? 'Генерируем...' : 'Сформировать'}</button></div>
      ${aiRecommendationsError ? `<div class="authStatus integrationStatus">${escapeHtml(aiRecommendationsError)}</div>` : ''}
      ${clientAiRecommendations?.recommendations?.length ? `
        <div class="aiDraftGrid">
          ${clientAiRecommendations.recommendations.map((item) => `<article><span>${escapeHtml(item.priority || 'medium')}</span><h3>${escapeHtml(item.title || 'Рекомендация')}</h3><p>${escapeHtml(item.description || item.reason || '')}</p><small>${escapeHtml(item.expected_effect || item.effort || '')}</small></article>`).join('')}
        </div>
      ` : '<div class="authStatus integrationStatus">AI-рекомендаций пока нет.</div>'}
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
    <section class="panel aiQuickActions"><h3>Быстрые промпты</h3><div class="heroActions">
      <button class="secondaryButton" data-ai-prompt="audit" ${aiLoading ? 'disabled' : ''}>Аудит</button>
      <button class="secondaryButton" data-ai-prompt="recommendations" ${aiLoading ? 'disabled' : ''}>Рекомендации</button>
      <button class="secondaryButton" data-ai-prompt="report" ${aiLoading ? 'disabled' : ''}>Отчёт</button>
      <button class="secondaryButton" data-ai-prompt="questions" ${aiLoading ? 'disabled' : ''}>Вопросы клиенту</button>
    </div>${aiError ? `<div class="authStatus integrationStatus">${escapeHtml(aiError)}</div>` : ''}${aiResult ? `<pre class="aiResult">${escapeHtml(aiResult.text || aiResult.answer || JSON.stringify(aiResult, null, 2))}</pre>` : ''}</section>
  `;
}

export function renderAiAssistantContent(context) {
  return `
    ${renderAiAssistantIntro(context)}
    <div class="aiGrid">
      ${renderAiStatusPanel(context)}
      ${renderAiPromptDebugPanel(context)}
    </div>
    ${renderAiChat(context)}
    ${renderClientAiRecommendations(context)}
    ${renderAiQuickActions(context)}
  `;
}

export const SETTINGS_PAGE_ID = 'settings';

export const settingsPage = {
  id: SETTINGS_PAGE_ID,
  title: 'Настройки',
  description: 'AI, OpenRouter, профиль и технический API-адрес кабинета.',
};

export function settingsPageContract() {
  return {
    routeId: SETTINGS_PAGE_ID,
    requiredContext: [
      'currentEmail',
      'apiBaseDraft',
      'apiBase',
      'backendClientsAvailable',
      'aiStatus',
      'aiModelSettings',
    ],
    legacyRenderer: 'renderSettings',
    extractionStatus: 'content-composer-ready',
    extractedBuilders: ['renderSettingsContent'],
  };
}

function presetLabel(preset) {
  return {
    economy: 'Эконом',
    balanced: 'Баланс',
    advanced: 'Максимум',
    deep: 'Максимум',
  }[preset] || preset || 'Баланс';
}

export function renderSettingsContent({
  currentEmail = '',
  apiBaseDraft = '',
  apiBase = '',
  backendClientsAvailable = false,
  aiStatus = {},
  selectedAiModel = '',
  selectedAiPreset = 'balanced',
  aiResolvedMaxTokens = 2500,
  aiMaxTokensMode = 'compact',
  aiToolResultsMode = 'summary',
  aiChatHistoryLimit = 3,
  aiSearchQueryLimit = '20',
  aiCompactContext = true,
  escapeHtml,
}) {
  const models = Array.isArray(aiStatus.models) ? aiStatus.models : [];
  const modelOptions = models.map((model) => `
    <option value="${escapeHtml(model.id)}" ${selectedAiModel === model.id ? 'selected' : ''}>
      ${escapeHtml(model.name || model.label || model.id)}
    </option>
  `).join('');
  const selectedModel = models.find((model) => model.id === selectedAiModel) || models[1] || models[0] || {};

  return `
    <section class="panel settingsHeroPanel">
      <div class="panelHeader">
        <div>
          <h2>Настройки</h2>
          <p>Здесь собраны AI-модель, лимиты контекста, OpenRouter и профиль. На странице AI-аналитика остаётся только чат.</p>
        </div>
      </div>
    </section>

    <section class="panel aiSettingsPanel">
      <div class="panelHeader">
        <div>
          <h3>AI и OpenRouter</h3>
          <p>${escapeHtml(aiStatus.message || 'Статус OpenRouter неизвестен')}</p>
        </div>
        <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'Готов' : 'Нет ключа'}</span>
      </div>

      <div class="aiModelSummary">
        <article><span>Текущая модель</span><strong>${escapeHtml(selectedModel.name || selectedAiModel)}</strong></article>
        <article><span>Профиль</span><strong>${escapeHtml(presetLabel(selectedAiPreset))}</strong></article>
        <article><span>Лимит ответа</span><strong>${escapeHtml(String(aiResolvedMaxTokens))} токенов</strong></article>
      </div>

      <div class="authStatus integrationStatus">
        В production-интерфейсе доступны только три контролируемые модели. Произвольные model ID используются только в eval-инструментах, не в кабинете.
      </div>

      <div class="aiModelSettings">
        <label>Модель
          <select data-ai-model>${modelOptions}</select>
        </label>
        <label>Профиль токенов
          <select data-ai-preset>
            <option value="economy" ${selectedAiPreset === 'economy' ? 'selected' : ''}>Эконом · быстрые регулярные проверки</option>
            <option value="balanced" ${selectedAiPreset === 'balanced' ? 'selected' : ''}>Баланс · основной анализ кампаний</option>
            <option value="advanced" ${selectedAiPreset === 'advanced' || selectedAiPreset === 'deep' ? 'selected' : ''}>Максимум · глубокий разбор</option>
          </select>
        </label>
        <label>AI-контекст
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
        <label>Глубина истории чата
          <select data-ai-chat-history-limit>
            <option value="1" ${Number(aiChatHistoryLimit) === 1 ? 'selected' : ''}>1 сообщение</option>
            <option value="3" ${Number(aiChatHistoryLimit) === 3 ? 'selected' : ''}>3 сообщения</option>
            <option value="6" ${Number(aiChatHistoryLimit) === 6 ? 'selected' : ''}>6 сообщений</option>
          </select>
        </label>
        <label>Лимит поисковых запросов
          <input data-ai-search-query-limit value="${escapeHtml(aiSearchQueryLimit)}" inputmode="numeric" />
        </label>
        <label class="checkboxLabel"><input type="checkbox" data-ai-compact-context ${aiCompactContext ? 'checked' : ''} /> Сжимать контекст перед отправкой</label>
      </div>
    </section>

    <section class="panel profileSettingsPanel">
      <div class="panelHeader">
        <div>
          <h3>Профиль и API</h3>
          <p>Минимальные настройки кабинета и backend API для локальной разработки.</p>
        </div>
      </div>
      <div class="insightGrid">
        <article><span>Email</span><strong>${escapeHtml(currentEmail || 'не указан')}</strong></article>
        <article><span>Backend</span><strong>${escapeHtml(backendClientsAvailable ? 'подключён' : 'не проверен')}</strong></article>
        <article><span>API</span><strong>${escapeHtml(apiBase)}</strong></article>
      </div>
      <form data-api-base-form class="settingsForm">
        <label>Backend API URL</label>
        <div class="settingsRow">
          <input name="apiBase" value="${escapeHtml(apiBaseDraft)}" placeholder="https://directpilot-ai-backend-mvp.vercel.app/api/v1" />
          <button class="secondaryButton" type="submit">Сохранить API URL</button>
        </div>
        <small>Используйте только backend DirectPilot AI. Секреты и OAuth-токены не хранятся во frontend.</small>
      </form>
    </section>
  `;
}

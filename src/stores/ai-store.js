export const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';

export const DEFAULT_AI_CHAT_MESSAGE = {
  role: 'assistant',
  content: 'Здравствуйте! Я AI-аналитик DirectPilot. Спросите про Директ, Метрику, CPA, цели или рекомендации — я соберу данные через MCP-инструменты и отвечу по контексту.',
};

export const DEFAULT_AI_CHAT_INPUT = 'Почему растёт CPA и что проверить в Яндекс.Метрике?';

export const DEFAULT_AI_STATUS = {
  models: [],
  configured: false,
  message: 'Статус OpenRouter ещё не загружен.',
};

export const AI_PRESETS = {
  economy: {
    maxTokens: 2500,
    targetContextTokens: 3500,
    includeRawToolResults: false,
  },
  balanced: {
    maxTokens: 5000,
    targetContextTokens: 9000,
    includeRawToolResults: false,
  },
  deep: {
    maxTokens: 9000,
    targetContextTokens: 18000,
    includeRawToolResults: true,
  },
};

export function createInitialAiChatState() {
  return {
    messages: [{ ...DEFAULT_AI_CHAT_MESSAGE }],
    input: DEFAULT_AI_CHAT_INPUT,
    loading: false,
    error: '',
    errorDetails: null,
    toolTraces: [],
    selectedCampaignName: '',
  };
}

export function createInitialAiModelState() {
  return {
    status: { ...DEFAULT_AI_STATUS },
    model: 'openrouter/auto',
    customModel: 'openai/gpt-4o',
    preset: 'economy',
    maxTokensMode: 'compact',
    compactContext: true,
    toolResultsMode: 'summary',
    chatHistoryLimit: 3,
    searchQueryLimit: '20',
  };
}

export function createInitialAiGenerationState() {
  return {
    loading: false,
    result: null,
    error: '',
    promptDebug: null,
    promptDebugLoading: false,
    promptDebugError: '',
    recommendationsLoading: false,
    recommendationsError: '',
    clientRecommendations: null,
    memoryStatus: '',
  };
}

export function normalizeAiStatus(payload) {
  if (!payload || typeof payload !== 'object') {
    return { ...DEFAULT_AI_STATUS };
  }

  return {
    models: Array.isArray(payload.models) ? payload.models : [],
    configured: Boolean(payload.configured),
    message: payload.message || DEFAULT_AI_STATUS.message,
  };
}

export function activeAiModel(modelState) {
  if (!modelState) return 'openrouter/auto';
  return modelState.model === CUSTOM_MODEL_VALUE
    ? modelState.customModel?.trim() || 'openrouter/auto'
    : modelState.model || 'openrouter/auto';
}

export function activeAiBudget(modelState) {
  const preset = modelState?.preset || 'economy';
  const base = AI_PRESETS[preset] || AI_PRESETS.economy;

  return {
    ...base,
    includeRawToolResults: preset === 'balanced'
      ? modelState?.toolResultsMode === 'raw'
      : base.includeRawToolResults,
  };
}

export function aiConversationForRequest(messages, limit = 3) {
  const safeLimit = Number(limit) || 3;
  return (Array.isArray(messages) ? messages : [])
    .slice(-safeLimit)
    .map((messageItem) => ({
      role: messageItem.role,
      content: messageItem.content,
    }));
}

export function createAiChatRequestPayload({
  clientId,
  message,
  modelState,
  chatState,
  businessContext,
}) {
  const budget = activeAiBudget(modelState);

  return {
    client_id: clientId || null,
    message,
    model: activeAiModel(modelState),
    max_tokens: budget.maxTokens,
    target_context_tokens: modelState?.maxTokensMode === 'deep' ? 18000 : budget.targetContextTokens,
    include_raw_tool_results: modelState?.toolResultsMode === 'raw' || budget.includeRawToolResults,
    compact_context: modelState?.compactContext !== false,
    include_business_context: true,
    business_context: businessContext || null,
    campaign_name: chatState?.selectedCampaignName || null,
    search_query_limit: Number(modelState?.searchQueryLimit) || 20,
    conversation: aiConversationForRequest(chatState?.messages, modelState?.chatHistoryLimit),
  };
}

export function createAiPromptDebugParams(modelState, selectedCampaignName = '', chatState = null) {
  const budget = activeAiBudget(modelState);
  const message = String(chatState?.input || '').trim();
  const history = aiConversationForRequest(chatState?.messages, modelState?.chatHistoryLimit);
  const params = new URLSearchParams({
    mode: 'chat',
    model: activeAiModel(modelState),
    max_tokens: String(budget.maxTokens),
    preset: modelState?.preset || 'economy',
    ai_preset: modelState?.preset || 'economy',
    max_tokens_mode: modelState?.maxTokensMode || 'compact',
    compact_context: modelState?.compactContext !== false ? 'true' : 'false',
    tool_results_mode: modelState?.toolResultsMode || 'summary',
    chat_history_limit: String(modelState?.chatHistoryLimit || 3),
    search_query_limit: modelState?.searchQueryLimit || '20',
    include_business_context: 'true',
  });

  if (message) params.set('message', message);
  if (history.length) params.set('history_json', JSON.stringify(history));
  if (selectedCampaignName) params.set('selected_campaign_name', selectedCampaignName);
  return params;
}

export function addAiChatMessage(chatState, message) {
  return {
    ...chatState,
    messages: [...(chatState?.messages || []), message],
  };
}

export function resetAiChatState() {
  return createInitialAiChatState();
}

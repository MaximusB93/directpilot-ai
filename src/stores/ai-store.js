export const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';
export const DEFAULT_PRODUCTION_AI_MODEL = 'qwen/qwen3-14b';
export const PRODUCTION_AI_MODELS = [
  {
    id: 'mistralai/mistral-small-3.2-24b-instruct',
    name: 'Mistral Small 3.2 · Эконом',
    tier: 'economy',
    description: 'Быстрые регулярные проверки и короткие ответы.',
  },
  {
    id: DEFAULT_PRODUCTION_AI_MODEL,
    name: 'Qwen3 14B · Баланс',
    tier: 'balanced',
    description: 'Основной режим для анализа кампаний, запросов и CPA.',
  },
  {
    id: 'deepseek/deepseek-chat-v3.1',
    name: 'DeepSeek V3.1 · Глубокий анализ',
    tier: 'advanced',
    description: 'Глубокий разбор сложных аудитов и спорных выводов.',
  },
];

export function productionAiModelIds() {
  return PRODUCTION_AI_MODELS.map((model) => model.id);
}

export function normalizeProductionAiModel(modelId) {
  const model = String(modelId || '').trim();
  return productionAiModelIds().includes(model) ? model : DEFAULT_PRODUCTION_AI_MODEL;
}

export function productionAiModelsFromStatus(models = []) {
  const byId = new Map((Array.isArray(models) ? models : []).map((model) => [model.id, model]));
  return PRODUCTION_AI_MODELS.map((fallback) => ({ ...fallback, ...(byId.get(fallback.id) || {}) }));
}

export const DEFAULT_AI_CHAT_MESSAGE = {
  role: 'assistant',
  content: 'Здравствуйте! Я AI-аналитик DirectPilot. Спросите про Директ, Метрику, CPA, цели или рекомендации — я соберу данные через MCP-инструменты и отвечу по контексту.',
};

export const DEFAULT_AI_CHAT_INPUT = 'Почему растёт CPA и что проверить в Яндекс.Метрике?';

export const DEFAULT_AI_STATUS = {
  models: [],
  presets: [],
  configured: false,
  message: 'Статус OpenRouter ещё не загружен.',
};

export const AI_PRESETS = {
  economy: {
    maxTokens: 1200,
    targetContextTokens: 3500,
    includeRawToolResults: false,
  },
  balanced: {
    maxTokens: 2500,
    targetContextTokens: 9000,
    includeRawToolResults: false,
  },
  advanced: {
    maxTokens: 5000,
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
    model: DEFAULT_PRODUCTION_AI_MODEL,
    customModel: '',
    preset: 'balanced',
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

export const TERMINAL_AI_AUDIT_STATUSES = new Set(['completed', 'failed', 'cancelled']);

export function createInitialAiAuditState() {
  return {
    job: null,
    loading: false,
    error: '',
    loadedFor: '',
    completedShownJobId: '',
  };
}

export function isTerminalAiAuditStatus(status) {
  return TERMINAL_AI_AUDIT_STATUSES.has(String(status || ''));
}

export function requiresStagedAudit(message) {
  const normalized = String(message || '').toLowerCase().replaceAll('ё', 'е').replace(/\s+/g, ' ').trim();
  return [
    'полный аудит',
    'аудит всего аккаунта',
    'аудит по чеклисту',
    'аудит по чек-листу',
    'проведи аудит',
    'все критические проблемы',
    'покажи критические проблемы',
    'комплексный анализ',
    'полный разбор кампаний',
  ].some((marker) => normalized.includes(marker));
}

export function normalizeAiStatus(payload) {
  if (!payload || typeof payload !== 'object') {
    return { ...DEFAULT_AI_STATUS };
  }

  return {
    models: productionAiModelsFromStatus(payload.models),
    presets: Array.isArray(payload.presets) ? payload.presets : [],
    configured: Boolean(payload.configured),
    message: payload.message || DEFAULT_AI_STATUS.message,
  };
}

export function activeAiModel(modelState) {
  if (!modelState) return DEFAULT_PRODUCTION_AI_MODEL;
  return normalizeProductionAiModel(modelState.model);
}

export function activeAiBudget(modelState) {
  const preset = modelState?.preset === 'deep' ? 'advanced' : (modelState?.preset || 'economy');
  const base = AI_PRESETS[preset] || AI_PRESETS.economy;
  const backendPreset = (modelState?.status?.presets || []).find((item) => item.id === preset);
  const backendMaxTokens = Number(backendPreset?.max_tokens ?? backendPreset?.maxTokens);

  return {
    ...base,
    maxTokens: Number.isFinite(backendMaxTokens) && backendMaxTokens > 0 ? backendMaxTokens : base.maxTokens,
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
  const preset = modelState?.preset === 'deep' ? 'advanced' : (modelState?.preset || 'economy');

  return {
    client_id: clientId || null,
    message,
    model: activeAiModel(modelState),
    ai_preset: preset,
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

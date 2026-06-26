export const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';

export const DEFAULT_AI_CHAT_MESSAGE = {
  role: 'assistant',
  content: 'Здравствуйте! Я AI-аналитик DirectPilot. Спросите про Директ, Метрику, CPA, цели или рекомендации — я соберу данные через MCP-инструменты и отвечу по контексту.',
};

export function createInitialAiChatState() {
  return {
    messages: [{ ...DEFAULT_AI_CHAT_MESSAGE }],
    input: 'Почему растёт CPA и что проверить в Яндекс.Метрике?',
    loading: false,
    error: '',
    errorDetails: null,
    toolTraces: [],
    selectedCampaignName: '',
  };
}

export function createInitialAiModelState() {
  return {
    status: { models: [], configured: false, message: 'Статус OpenRouter ещё не загружен.' },
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

import * as aiStore from '../stores/ai-store.js';

export function createAiModelStateSnapshot({
  aiStatus,
  selectedAiModel,
  customAiModel,
  selectedAiPreset,
  aiMaxTokensMode,
  aiCompactContext,
  aiToolResultsMode,
  aiChatHistoryLimit,
  aiSearchQueryLimit,
}) {
  return {
    status: aiStatus,
    model: selectedAiModel,
    customModel: customAiModel,
    preset: selectedAiPreset,
    maxTokensMode: aiMaxTokensMode,
    compactContext: aiCompactContext,
    toolResultsMode: aiToolResultsMode,
    chatHistoryLimit: aiChatHistoryLimit,
    searchQueryLimit: aiSearchQueryLimit,
  };
}

export function createAiChatStateSnapshot({
  aiChatMessages,
  aiChatInput,
  aiChatLoading,
  aiChatError,
  aiChatErrorDetails,
  aiChatToolTraces,
  aiChatSelectedCampaignName,
}) {
  return {
    messages: aiChatMessages,
    input: aiChatInput,
    loading: aiChatLoading,
    error: aiChatError,
    errorDetails: aiChatErrorDetails,
    toolTraces: aiChatToolTraces,
    selectedCampaignName: aiChatSelectedCampaignName,
  };
}

export function activeAiModel(modelState) {
  return aiStore.activeAiModel(modelState);
}

export function activeAiBudget(modelState) {
  return aiStore.activeAiBudget(modelState);
}

export function createAiChatRequestPayload({
  clientId,
  message,
  modelState,
  chatState,
  businessContext,
}) {
  return aiStore.createAiChatRequestPayload({
    clientId,
    message,
    modelState,
    chatState,
    businessContext,
  });
}

export function createAiPromptDebugParams(modelState, selectedCampaignName = '') {
  return aiStore.createAiPromptDebugParams(modelState, selectedCampaignName);
}

export async function loadAiStatusFlow({
  aiService,
  onStatus,
  onFinally,
}) {
  let status;

  try {
    status = aiStore.normalizeAiStatus(await aiService.fetchOpenRouterStatus());
  } catch (error) {
    status = aiStore.normalizeAiStatus({
      configured: false,
      models: [],
      message: 'Backend недоступен, OpenRouter не проверен.',
    });
  } finally {
    onStatus?.(status);
    onFinally?.();
  }

  return status;
}

export async function loadAiPromptDebugFlow({
  selectedClientId,
  params,
  aiService,
  onMissingClient,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId) {
    const message = 'Сначала выберите клиента.';
    onMissingClient?.(message);
    return { status: 'missing-client', error: message };
  }

  onStart?.();

  try {
    const promptDebug = await aiService.fetchAiPromptDebug(selectedClientId, params);
    onSuccess?.(promptDebug);
    return { status: 'success', promptDebug };
  } catch (error) {
    const message = error.message || 'Не удалось проверить размер AI-контекста';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function generateAiInsightFlow({
  prompt,
  aiService,
  model,
  maxTokens,
  preset,
  businessContext,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  onStart?.();

  try {
    const result = await aiService.generateAiInsight({
      prompt,
      model,
      max_tokens: maxTokens,
      preset,
      business_context: businessContext,
    });
    onSuccess?.(result);
    return { status: 'success', result };
  } catch (error) {
    const message = error.message || 'Не удалось получить AI-ответ';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function saveAiMemoryNoteFlow({
  selectedClientId,
  note,
  businessContextService,
  onStart,
  onSuccess,
  onError,
}) {
  if (!selectedClientId || !note) {
    return { status: 'skipped' };
  }

  onStart?.('Сохраняем вывод в память проекта...');

  try {
    const payload = await businessContextService.saveBusinessContextMemoryNote(selectedClientId, note);
    const message = 'AI-вывод сохранён в память проекта.';
    onSuccess?.(payload, message);
    return { status: 'success', payload };
  } catch (error) {
    const message = error.message || 'Не удалось сохранить вывод в память проекта.';
    onError?.(message, error);
    return { status: 'error', error: message };
  }
}

export async function requestAiRecommendationsFlow({
  selectedClientId,
  params,
  aiService,
  saveMemoryNote,
  onMissingClient,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId) {
    const message = 'Сначала выберите клиента.';
    onMissingClient?.(message);
    return { status: 'missing-client', error: message };
  }

  onStart?.();

  try {
    const payload = await aiService.fetchClientAiRecommendations(selectedClientId, params);
    onSuccess?.(payload);

    if (payload.business_context_memory_note) {
      await saveMemoryNote?.(payload.business_context_memory_note);
    }

    return { status: 'success', payload };
  } catch (error) {
    const message = error.message || 'Не удалось сформировать AI-рекомендации';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function sendAiChatMessageFlow({
  message,
  loading,
  currentChatState,
  createRequestPayload,
  addChatMessage,
  aiService,
  saveMemoryNote,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  const text = String(message || '').trim();
  if (!text || loading) {
    return { status: 'skipped' };
  }

  const userMessages = addChatMessage(currentChatState(), { role: 'user', content: text }).messages;
  onStart?.({ text, messages: userMessages });

  try {
    const payload = await aiService.requestAiChat(createRequestPayload(text));
    const assistantMessages = addChatMessage(currentChatState(), { role: 'assistant', content: payload.answer || 'Нет ответа.' }).messages;
    onSuccess?.({ payload, messages: assistantMessages, toolTraces: payload.tool_traces || [] });

    if (payload.business_context_memory_note) {
      await saveMemoryNote?.(payload.business_context_memory_note);
    }

    return { status: 'success', payload };
  } catch (error) {
    const payload = error.payload || {};
    const messageText = error.message || 'AI-чат не вернул ответ';
    let retryMessages = null;

    if (payload.retry_suggestion) {
      retryMessages = addChatMessage(currentChatState(), { role: 'assistant', content: `Не смог собрать ответ: ${payload.retry_suggestion}` }).messages;
    }

    onError?.({ message: messageText, payload, messages: retryMessages });
    return { status: 'error', error: messageText, payload };
  } finally {
    onFinally?.();
  }
}

export function createAiAssistantPageContext({
  selectedClientId,
  selectedClient,
  aiStatus,
  selectedAiModel,
  customAiModel,
  customModelValue,
  selectedAiPreset,
  aiMaxTokensMode,
  aiToolResultsMode,
  aiChatHistoryLimit,
  aiSearchQueryLimit,
  aiCompactContext,
  aiPromptDebugLoading,
  aiPromptDebugError,
  aiPromptDebug,
  campaignOptions,
  aiChatSelectedCampaignName,
  aiChatMessages,
  aiChatInput,
  aiChatLoading,
  aiChatError,
  aiChatErrorDetails,
  aiChatToolTraces,
  aiRecommendationsLoading,
  aiRecommendationsError,
  clientAiRecommendations,
  aiLoading,
  aiError,
  aiResult,
  performanceSummary,
  businessContext,
  optimizationActions,
  formatNumberSafe,
  escapeHtml,
}) {
  return {
    selectedClientId,
    selectedClient,
    aiStatus,
    selectedAiModel,
    customAiModel,
    customModelValue,
    selectedAiPreset,
    aiMaxTokensMode,
    aiToolResultsMode,
    aiChatHistoryLimit,
    aiSearchQueryLimit,
    aiCompactContext,
    aiPromptDebugLoading,
    aiPromptDebugError,
    aiPromptDebug,
    campaignOptions,
    aiChatSelectedCampaignName,
    aiChatMessages,
    aiChatInput,
    aiChatLoading,
    aiChatError,
    aiChatErrorDetails,
    aiChatToolTraces,
    aiRecommendationsLoading,
    aiRecommendationsError,
    clientAiRecommendations,
    aiLoading,
    aiError,
    aiResult,
    performanceSummary,
    businessContext,
    optimizationActions,
    formatNumberSafe,
    escapeHtml,
  };
}

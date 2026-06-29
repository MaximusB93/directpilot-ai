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

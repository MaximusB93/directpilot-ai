import * as aiStore from './ai-store.js';

export function createAiFeatureState() {
  const modelState = aiStore.createInitialAiModelState();
  const generationState = aiStore.createInitialAiGenerationState();
  const chatState = aiStore.createInitialAiChatState();

  return {
    model: {
      status: modelState.status,
      selectedModel: modelState.model,
      customModel: modelState.customModel,
      selectedPreset: modelState.preset,
      maxTokensMode: modelState.maxTokensMode,
      compactContext: modelState.compactContext,
      toolResultsMode: modelState.toolResultsMode,
      chatHistoryLimit: modelState.chatHistoryLimit,
      searchQueryLimit: modelState.searchQueryLimit,
    },
    generation: {
      loading: generationState.loading,
      result: generationState.result,
      error: generationState.error,
      promptDebug: generationState.promptDebug,
      promptDebugLoading: generationState.promptDebugLoading,
      promptDebugError: generationState.promptDebugError,
      recommendationsLoading: generationState.recommendationsLoading,
      recommendationsError: generationState.recommendationsError,
      clientRecommendations: generationState.clientRecommendations,
      memoryStatus: generationState.memoryStatus,
    },
    chat: {
      messages: chatState.messages.map((message) => ({ ...message })),
      input: chatState.input,
      loading: chatState.loading,
      error: chatState.error,
      errorDetails: chatState.errorDetails,
      toolTraces: chatState.toolTraces,
      selectedCampaignName: chatState.selectedCampaignName,
    },
  };
}

export function resetAiClientScopedState(aiFeatureState) {
  aiFeatureState.generation.clientRecommendations = null;
}

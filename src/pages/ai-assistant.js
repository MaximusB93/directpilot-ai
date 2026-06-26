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
    extractionStatus: 'contract-only',
    nextStep: 'Move AI assistant page after dashboard, clients and integrations are stable because this area has the highest state density.',
  };
}

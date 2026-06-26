export const OPTIMIZATION_PAGE_ID = 'optimization';

export const optimizationPage = {
  id: OPTIMIZATION_PAGE_ID,
  title: 'Оптимизация',
  description: 'Диагностика, план оптимизации, черновики действий, согласование и безопасный предпросмотр.',
};

export function optimizationPageContract() {
  return {
    routeId: OPTIMIZATION_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
      'performanceSummary',
      'optimizationPlan',
      'optimizationActions',
      'optimizationFilter',
      'optimizationActionFilter',
      'optimizationExecutionPreviews',
    ],
    legacyRenderer: 'renderOptimization',
    extractionStatus: 'contract-only',
    nextStep: 'Move renderOptimization after sync/performance services and dashboard panels are extracted.',
  };
}

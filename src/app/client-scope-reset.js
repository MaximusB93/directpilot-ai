export function createClientScopeResetPatch({ activeView = 'dashboard' } = {}) {
  return {
    activeView,
    businessContext: null,
    businessContextDraft: null,
    clientYandexIntegration: null,
    syncJobs: [],
    perfSummary: null,
    optimizationPlan: null,
    optimizationActions: [],
    optimizationActionsLoadedFor: '',
    optimizationExecutionPreviews: {},
    journalLoadedFor: '',
  };
}

export function applyClientScopeResetPatch(applyPatch, patch = createClientScopeResetPatch()) {
  if (typeof applyPatch !== 'function') return patch;
  applyPatch(patch);
  return patch;
}

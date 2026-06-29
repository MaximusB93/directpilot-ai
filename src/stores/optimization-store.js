export function normalizeOptimizationPlan(payload) {
  if (!payload) return null;
  return {
    ...payload,
    dailyBudgetRecommendations: Array.isArray(payload.daily_budget_recommendations) ? payload.daily_budget_recommendations : payload.dailyBudgetRecommendations || [],
    deviceAdjustments: Array.isArray(payload.device_adjustments) ? payload.device_adjustments : payload.deviceAdjustments || [],
    generatedAt: payload.generated_at || payload.generatedAt || '',
  };
}

export function normalizeOptimizationAction(action = {}) {
  return {
    ...action,
    actionType: action.action_type || action.actionType,
    entityType: action.entity_type || action.entityType,
    entityId: action.entity_id || action.entityId,
    entityName: action.entity_name || action.entityName,
    currentValue: action.current_value ?? action.currentValue,
    proposedValue: action.proposed_value ?? action.proposedValue,
    createdAt: action.created_at || action.createdAt,
    updatedAt: action.updated_at || action.updatedAt,
  };
}

export function normalizeOptimizationPreview(payload = {}) {
  return {
    ...payload,
    actionId: payload.action_id || payload.actionId,
    steps: Array.isArray(payload.steps) ? payload.steps : [],
    warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
    directPayload: payload.direct_payload || payload.directPayload || null,
    canApply: Boolean(payload.can_apply ?? payload.canApply),
  };
}

export function normalizeOptimizationActions(payload) {
  return Array.isArray(payload) ? payload.map(normalizeOptimizationAction) : [];
}

export function getFilteredOptimizationActions(actions = [], filter = 'all') {
  return actions.filter((action) => filter === 'all' || action.status === filter);
}

export function replaceOptimizationAction(actions = [], updatedAction) {
  if (!updatedAction?.id) return actions;
  return actions.map((action) => action.id === updatedAction.id ? updatedAction : action);
}

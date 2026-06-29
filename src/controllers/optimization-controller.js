import * as optimizationStore from '../stores/optimization-store.js';

export async function loadOptimizationPlanFlow({
  selectedClientId,
  loading,
  optimizationService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || loading) return { status: 'skipped' };

  onStart?.('Формируем план оптимизации...');

  try {
    const payload = await optimizationService.fetchOptimizationPlan(selectedClientId);
    const plan = optimizationStore.normalizeOptimizationPlan(payload);
    onSuccess?.(plan, 'План оптимизации обновлён.');
    return { status: 'success', plan };
  } catch (error) {
    const message = error.message || 'Не удалось сформировать план оптимизации.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function loadOptimizationActionsFlow({
  selectedClientId,
  loading,
  loadedFor,
  filter,
  force = false,
  optimizationService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || loading) return { status: 'skipped' };
  if (!force && loadedFor === selectedClientId) return { status: 'cached' };

  onStart?.('Загружаем черновики согласования...');

  try {
    const payload = await optimizationService.fetchOptimizationActions(selectedClientId, filter);
    const actions = optimizationStore.normalizeOptimizationActions(payload);
    const message = actions.length ? 'Черновики согласования загружены.' : 'Черновиков пока нет. Сохраните план оптимизации как черновики.';
    onSuccess?.(actions, selectedClientId, message);
    return { status: 'success', actions };
  } catch (error) {
    const message = error.message || 'Не удалось загрузить черновики согласования.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function createOptimizationDraftsFromPlanFlow({
  selectedClientId,
  loading,
  optimizationService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || loading) return { status: 'skipped' };

  onStart?.('Сохраняем рекомендации как черновики...');

  try {
    const payload = await optimizationService.saveOptimizationPlanAsDrafts(selectedClientId);
    const actions = optimizationStore.normalizeOptimizationActions(payload);
    onSuccess?.(actions, selectedClientId, `Сохранено черновиков: ${actions.length}.`);
    return { status: 'success', actions };
  } catch (error) {
    const message = error.message || 'Не удалось сохранить черновики.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function updateOptimizationActionStatusFlow({
  selectedClientId,
  actionId,
  status,
  reviewerNote = '',
  actions,
  optimizationService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || !actionId) return { status: 'skipped' };

  onStart?.('Обновляем статус черновика...');

  try {
    const payload = await optimizationService.updateOptimizationAction(selectedClientId, actionId, {
      status,
      reviewer_note: reviewerNote,
    });
    const updated = optimizationStore.normalizeOptimizationAction(payload);
    const nextActions = optimizationStore.replaceOptimizationAction(actions, updated);
    onSuccess?.(nextActions, 'Статус черновика обновлён.');
    return { status: 'success', action: updated, actions: nextActions };
  } catch (error) {
    const message = error.message || 'Не удалось обновить черновик.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function loadOptimizationExecutionPreviewFlow({
  selectedClientId,
  actionId,
  currentPreview,
  optimizationService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || !actionId) return { status: 'skipped' };

  onStart?.(actionId, currentPreview?.data || null);

  try {
    const payload = await optimizationService.fetchOptimizationExecutionPreview(selectedClientId, actionId);
    const preview = optimizationStore.normalizeOptimizationPreview(payload);
    onSuccess?.(actionId, preview);
    return { status: 'success', preview };
  } catch (error) {
    const message = error.message || 'Не удалось загрузить предпросмотр применения';
    onError?.(actionId, message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

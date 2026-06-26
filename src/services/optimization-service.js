import { apiFetch } from '../core/api.js';

export async function fetchOptimizationPlan(clientId) {
  const response = await apiFetch(`/clients/${clientId}/optimization-plan`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить план оптимизации');
  return payload;
}

export async function fetchOptimizationActions(clientId, status = 'all') {
  const query = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : '';
  const response = await apiFetch(`/clients/${clientId}/optimization-actions${query}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить черновики согласования');
  return payload;
}

export async function saveOptimizationPlanAsDrafts(clientId) {
  const response = await apiFetch(`/clients/${clientId}/optimization-actions/from-plan`, { method: 'POST' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить черновики');
  return payload;
}

export async function updateOptimizationAction(clientId, actionId, values) {
  const response = await apiFetch(`/clients/${clientId}/optimization-actions/${actionId}`, {
    method: 'PATCH',
    body: JSON.stringify(values),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось обновить черновик');
  return payload;
}

export async function fetchOptimizationExecutionPreview(clientId, actionId) {
  const response = await apiFetch(`/clients/${clientId}/optimization-actions/${actionId}/execution-preview`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить предпросмотр применения');
  return payload;
}

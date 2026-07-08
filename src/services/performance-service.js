import { apiFetch } from '../core/api.js';

export async function fetchPerformanceSummary(clientId) {
  const response = await apiFetch(`/clients/${clientId}/performance-summary`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить сводку');
  return payload;
}

export async function fetchPerformanceRangeSummary(clientId, { preset = 'yesterday', dateFrom = '', dateTo = '' } = {}) {
  const params = new URLSearchParams();
  params.set('preset', preset || 'yesterday');
  if (preset === 'custom') {
    params.set('date_from', dateFrom || '');
    params.set('date_to', dateTo || '');
  }
  const response = await apiFetch(`/clients/${clientId}/performance-range?${params.toString()}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить данные за выбранный период');
  return payload;
}

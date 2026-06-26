import { apiFetch } from '../core/api.js';

export async function fetchPerformanceSummary(clientId) {
  const response = await apiFetch(`/clients/${clientId}/performance-summary`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить сводку');
  return payload;
}

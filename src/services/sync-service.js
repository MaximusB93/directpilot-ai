import { apiFetch } from '../core/api.js';

export async function runClientSync(clientId) {
  const response = await apiFetch(`/clients/${clientId}/sync`, { method: 'POST' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Ошибка синхронизации');
  return payload;
}

export async function fetchSyncJobs(clientId) {
  const response = await apiFetch(`/clients/${clientId}/sync/jobs`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить историю синхронизаций');
  return Array.isArray(payload) ? payload : [];
}

import { apiFetch } from '../core/api.js';

export async function fetchBusinessContext(clientId) {
  const response = await apiFetch(`/clients/${clientId}/business-context`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить контекст бизнеса');
  return payload;
}

export async function saveBusinessContext(clientId, values) {
  const response = await apiFetch(`/clients/${clientId}/business-context`, {
    method: 'PUT',
    body: JSON.stringify(values),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить контекст бизнеса');
  return payload;
}

export async function saveBusinessContextMemoryNote(clientId, note) {
  const response = await apiFetch(`/clients/${clientId}/business-context/memory-note`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить в память проекта');
  return payload;
}

import { apiFetch } from '../core/api.js';

export async function fetchClients() {
  const response = await apiFetch('/clients');
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `Backend responded with ${response.status}`);
  if (!Array.isArray(payload)) throw new Error('Invalid clients payload');
  return payload;
}

export async function createClient(client) {
  const response = await apiFetch('/clients', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: client.id,
      name: client.name,
      direct_login: client.directLogin === 'Не подключен' ? null : client.directLogin,
      metrica_counter: client.metricaCounter === 'Не подключен' ? null : client.metricaCounter,
      yandex_account_id: client.yandexAccountId || null,
      target_cpa: client.targetCpa || null,
      main_goal_id: client.mainGoalId || null,
      conversion_goal_ids: client.conversionGoalIds || client.mainGoalId || null,
      notes: client.notes || null,
      segment: client.segment,
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить клиента в базе данных');
  return payload;
}

export async function updateClient(clientId, values) {
  const response = await apiFetch(`/clients/${clientId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить настройки клиента');
  return payload;
}

export async function deleteClient(clientId) {
  const response = await apiFetch(`/clients/${clientId}`, { method: 'DELETE' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось удалить клиента');
  return payload;
}

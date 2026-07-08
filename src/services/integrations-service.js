import { apiFetch } from '../core/api.js';

export async function startYandexOAuth() {
  const response = await apiFetch('/auth/yandex/start');
  const payload = await response.json();
  if (!response.ok || !payload.auth_url) throw new Error(payload.detail || payload.message || 'OAuth URL не получен');
  return payload;
}

export async function deleteYandexAccount(clientId, accountId) {
  const response = await apiFetch(`/clients/${clientId}/integrations/yandex/accounts/${accountId}`, { method: 'DELETE' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось удалить Яндекс-аккаунт');
  return payload;
}

export async function fetchYandexStatus() {
  const response = await apiFetch('/auth/yandex/status');
  return response.ok ? response.json() : {};
}

export async function fetchClientYandexIntegration(clientId) {
  const response = await apiFetch(`/clients/${clientId}/integrations/yandex`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить привязку Яндекса');
  return payload;
}

export async function bindClientYandexIntegration(clientId, accountId) {
  const response = await apiFetch(`/clients/${clientId}/integrations/yandex`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yandex_account_id: accountId }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось привязать аккаунт');
  return payload;
}

export async function unbindClientYandexIntegration(clientId) {
  const response = await apiFetch(`/clients/${clientId}/integrations/yandex`, { method: 'DELETE' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось отвязать аккаунт');
  return payload;
}

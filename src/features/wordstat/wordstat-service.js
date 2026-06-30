import { apiFetch } from '../../core/api.js';

async function parseWordstatJsonResponse(response, fallbackMessage) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error(fallbackMessage);
  }

  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || fallbackMessage);
  }

  return payload;
}

export async function fetchWordstatConnection({ api = apiFetch } = {}) {
  const response = await api('/wordstat/connection');
  return parseWordstatJsonResponse(response, 'Не удалось проверить Wordstat');
}

export async function fetchWordstatDynamics(requestBody, { api = apiFetch } = {}) {
  const response = await api('/wordstat/dynamics/batch', {
    method: 'POST',
    body: JSON.stringify(requestBody),
  });
  return parseWordstatJsonResponse(response, 'Wordstat API не вернул данные');
}

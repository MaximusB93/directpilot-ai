import { apiFetch, API_BASE } from '../core/api.js';

export async function fetchOpenRouterStatus() {
  const response = await fetch(`${API_BASE}/ai/openrouter/status`);
  return response.ok ? response.json() : { models: [], configured: false, message: 'Не удалось получить статус OpenRouter.' };
}

export async function generateAiInsight(request) {
  const response = await apiFetch('/ai/openrouter/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'OpenRouter не вернул ответ');
  return payload;
}

export async function requestAiChat(request) {
  const response = await apiFetch('/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    const message = payload.message || payload.detail || 'AI-чат не вернул ответ';
    const error = new Error(message);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

export async function fetchClientAiRecommendations(clientId, request) {
  const response = await apiFetch(`/clients/${clientId}/ai/recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    const message = payload.message || payload.detail || 'Не удалось сформировать AI-рекомендации';
    const error = new Error(message);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

export async function fetchAiPromptDebug(clientId, params) {
  const query = params instanceof URLSearchParams ? params.toString() : new URLSearchParams(params).toString();
  const response = await apiFetch(`/clients/${clientId}/ai/prompt-debug?${query}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось проверить размер AI-контекста');
  return payload;
}

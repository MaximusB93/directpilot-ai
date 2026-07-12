import { AI_API_REQUEST_TIMEOUT_MS, apiFetch, API_BASE } from '../core/api.js';

const AI_TIMEOUT_MESSAGE = `AI-модель не успела завершить ответ за ${AI_API_REQUEST_TIMEOUT_MS / 1000} секунд. Запрос мог быть обработан backend, но ответ не был получен вовремя. Повторите запрос или выберите экономичную модель.`;

function aiRequestOptions(options) {
  return {
    ...options,
    timeoutMs: AI_API_REQUEST_TIMEOUT_MS,
    timeoutErrorCode: 'ai_request_timeout',
    timeoutMessage: AI_TIMEOUT_MESSAGE,
  };
}

function apiErrorMessage(payload, fallback) {
  if (typeof payload?.message === 'string') return payload.message;
  if (typeof payload?.detail === 'string') return payload.detail;
  if (payload?.detail && typeof payload.detail === 'object') {
    return payload.detail.message || fallback;
  }
  return fallback;
}

export async function fetchOpenRouterStatus() {
  const response = await fetch(`${API_BASE}/ai/openrouter/status`);
  return response.ok ? response.json() : { models: [], configured: false, message: 'Не удалось получить статус OpenRouter.' };
}

export async function generateAiInsight(request) {
  const response = await apiFetch('/ai/openrouter/generate', aiRequestOptions({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }));
  const payload = await response.json();
  if (!response.ok) throw new Error(apiErrorMessage(payload, 'OpenRouter не вернул ответ'));
  return payload;
}

export async function requestAiChat(request) {
  const response = await apiFetch('/ai/chat', aiRequestOptions({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }));
  const payload = await response.json();
  if (!response.ok || payload.error) {
    const message = apiErrorMessage(payload, 'AI-чат не вернул ответ');
    const error = new Error(message);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

export async function fetchClientAiRecommendations(clientId, request) {
  const response = await apiFetch(`/clients/${clientId}/ai/recommendations`, aiRequestOptions({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }));
  const payload = await response.json();
  if (!response.ok || payload.error) {
    const message = apiErrorMessage(payload, 'Не удалось сформировать AI-рекомендации');
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

async function auditJobRequest(path, options = {}) {
  const response = await apiFetch(path, aiRequestOptions(options));
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(apiErrorMessage(payload, 'Не удалось выполнить этап AI-аудита'));
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

export function createAiAuditJob(request) {
  return auditJobRequest('/ai/audits', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export function fetchAiAuditJob(jobId) {
  return auditJobRequest(`/ai/audits/${jobId}`);
}

export function advanceAiAuditJob(jobId, retry = false) {
  return auditJobRequest(`/ai/audits/${jobId}/advance`, {
    method: 'POST',
    body: JSON.stringify({ retry }),
  });
}

export function cancelAiAuditJob(jobId) {
  return auditJobRequest(`/ai/audits/${jobId}/cancel`, { method: 'POST' });
}

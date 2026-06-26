export const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
export const API_BASE = resolveApiBase();

export function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');

  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000/api/v1';
  }
  if (hostname === 'maximusb93.github.io') {
    return DEFAULT_PRODUCTION_API_BASE;
  }

  return `${origin}/api/v1`;
}

export function hasCustomApiBase() {
  return Boolean(window.localStorage.getItem('directpilot_api_base')?.trim());
}

export function saveApiBase(value) {
  const apiBase = String(value || '').trim().replace(/\/$/, '');
  if (apiBase) {
    window.localStorage.setItem('directpilot_api_base', apiBase);
  } else {
    window.localStorage.removeItem('directpilot_api_base');
  }
}

export function getSessionToken() {
  return window.localStorage.getItem('directpilot_session') || '';
}

export function clearSession() {
  window.localStorage.removeItem('directpilot_session');
  window.localStorage.removeItem('directpilot_email');
}

export function backendConnectionError() {
  return `Не удалось подключиться к backend. Проверьте Vercel URL или directpilot_api_base. Текущий API_BASE: ${API_BASE}`;
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export async function postJson(path, body, fallbackMessage = 'Не удалось выполнить запрос') {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (error) {
    throw new Error(backendConnectionError());
  }

  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }

  if (!response.ok) {
    throw new Error(payload.detail || fallbackMessage);
  }

  return payload;
}

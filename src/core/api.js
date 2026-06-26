import { escapeHtml } from './html.js';
import {
  clearSession,
  getCustomApiBase,
  getSessionToken,
  saveCustomApiBase,
} from './storage.js';

export { clearSession, escapeHtml, getSessionToken };

export const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
export const API_BASE = resolveApiBase();

export function resolveApiBase() {
  const custom = getCustomApiBase();
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
  return Boolean(getCustomApiBase());
}

export function saveApiBase(value) {
  saveCustomApiBase(value);
}

export function backendConnectionError() {
  return `Не удалось подключиться к backend. Проверьте Vercel URL или directpilot_api_base. Текущий API_BASE: ${API_BASE}`;
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

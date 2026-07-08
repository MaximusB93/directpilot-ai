import { escapeHtml } from './html.js';
import {
  clearSession,
  getCurrentEmail,
  getCustomApiBase,
  getSessionToken,
  saveCustomApiBase,
} from './storage.js';

export { clearSession, escapeHtml, getSessionToken };

export const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai-backend-mvp.vercel.app/api/v1';
export const API_BASE = resolveApiBase();

const API_CACHE_PREFIX = 'directpilot_api_cache_v1:';
const API_CACHE_MAX_AGE_MS = 2 * 60 * 1000;
const API_CACHE_STALE_MS = 20 * 60 * 1000;
const API_CACHEABLE_PATHS = [
  '/clients',
  '/integrations',
  '/auth/yandex',
  '/ai/openrouter/status',
];

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
  clearApiCache();
  saveCustomApiBase(value);
}

export function backendConnectionError() {
  return `Не удалось подключиться к backend. Проверьте Vercel URL или directpilot_api_base. Текущий API_BASE: ${API_BASE}`;
}

function apiCacheUserScope() {
  return getCurrentEmail() || 'anonymous';
}

function requestMethod(options = {}) {
  return String(options.method || 'GET').toUpperCase();
}

function normalizePath(path) {
  return String(path || '').trim();
}

function isCacheableGet(path, options = {}) {
  const normalizedPath = normalizePath(path);
  if (requestMethod(options) !== 'GET') return false;
  if (options.cache === 'no-store' || options.cache === 'reload') return false;
  if (options.skipDirectPilotCache) return false;
  return API_CACHEABLE_PATHS.some((prefix) => (
    normalizedPath === prefix || normalizedPath.startsWith(`${prefix}/`) || normalizedPath.startsWith(`${prefix}?`)
  ));
}

function cacheKey(path) {
  return `${API_CACHE_PREFIX}${apiCacheUserScope()}:${API_BASE}:${normalizePath(path)}`;
}

function makeJsonResponse(payload, { stale = false } = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    statusText: 'OK',
    headers: {
      'Content-Type': 'application/json',
      'X-DirectPilot-Cache': stale ? 'stale' : 'fresh',
    },
  });
}

function readApiCache(path) {
  try {
    const key = cacheKey(path);
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const cached = JSON.parse(raw);
    if (!cached || typeof cached.savedAt !== 'number' || cached.payload === undefined) return null;
    const age = Date.now() - cached.savedAt;
    if (age > API_CACHE_STALE_MS) {
      window.localStorage.removeItem(key);
      return null;
    }
    return { ...cached, age, fresh: age <= API_CACHE_MAX_AGE_MS };
  } catch (error) {
    window.localStorage.removeItem(cacheKey(path));
    return null;
  }
}

async function writeApiCache(path, response) {
  try {
    if (!response.ok) return;
    const clone = response.clone();
    const contentType = clone.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) return;
    const payload = await clone.json();
    window.localStorage.setItem(cacheKey(path), JSON.stringify({ savedAt: Date.now(), payload }));
  } catch (error) {
    // Cache is only an optimization. If it breaks, the app should not.
  }
}

export function clearApiCache() {
  try {
    const keys = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith(API_CACHE_PREFIX)) keys.push(key);
    }
    keys.forEach((key) => window.localStorage.removeItem(key));
  } catch (error) {
    // Ignore localStorage cleanup errors.
  }
}

function backgroundRefresh(path, options) {
  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  fetch(`${API_BASE}${path}`, { ...options, headers })
    .then((response) => writeApiCache(path, response))
    .catch(() => {});
}

export async function apiFetch(path, options = {}) {
  const method = requestMethod(options);
  const cacheable = isCacheableGet(path, options);
  if (cacheable) {
    const cached = readApiCache(path);
    if (cached?.fresh) {
      return makeJsonResponse(cached.payload);
    }
    if (cached) {
      backgroundRefresh(path, options);
      return makeJsonResponse(cached.payload, { stale: true });
    }
  }

  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401) {
    clearSession();
    clearApiCache();
    window.location.href = 'login.html';
    throw new Error('Authentication required');
  }

  if (cacheable) {
    writeApiCache(path, response);
  } else if (method !== 'GET' && response.ok) {
    clearApiCache();
  }

  return response;
}

export async function postJson(path, body, fallbackMessage = 'Не удалось выполнить запрос') {
  let response;
  try {
    response = await apiFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (error.message === 'Authentication required') {
      throw error;
    }
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

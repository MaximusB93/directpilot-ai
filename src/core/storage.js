export const STORAGE_KEYS = Object.freeze({
  apiBase: 'directpilot_api_base',
  session: 'directpilot_session',
  email: 'directpilot_email',
});

export function readStorage(key, fallback = '') {
  return window.localStorage.getItem(key) || fallback;
}

export function writeStorage(key, value) {
  const normalized = String(value || '').trim();
  if (normalized) {
    window.localStorage.setItem(key, normalized);
  } else {
    window.localStorage.removeItem(key);
  }
}

export function removeStorage(key) {
  window.localStorage.removeItem(key);
}

export function getSessionToken() {
  return readStorage(STORAGE_KEYS.session);
}

export function getCurrentEmail() {
  return readStorage(STORAGE_KEYS.email);
}

export function saveSession(sessionToken, email) {
  writeStorage(STORAGE_KEYS.session, sessionToken);
  writeStorage(STORAGE_KEYS.email, email);
}

export function clearSession() {
  removeStorage(STORAGE_KEYS.session);
  removeStorage(STORAGE_KEYS.email);
}

export function getCustomApiBase() {
  return readStorage(STORAGE_KEYS.apiBase).trim();
}

export function saveCustomApiBase(value) {
  const apiBase = String(value || '').trim().replace(/\/$/, '');
  writeStorage(STORAGE_KEYS.apiBase, apiBase);
}

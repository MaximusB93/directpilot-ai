const SELECTED_CLIENT_KEY = 'directpilot_selected_client_id';

export function selectedClientStorageKey(scopedStorageKey) {
  return scopedStorageKey(SELECTED_CLIENT_KEY);
}

export function loadSelectedClientId(scopedStorageKey, fallbackClientId = '') {
  return window.localStorage.getItem(selectedClientStorageKey(scopedStorageKey)) || fallbackClientId || '';
}

export function saveSelectedClientId(scopedStorageKey, clientId) {
  const key = selectedClientStorageKey(scopedStorageKey);
  if (clientId) {
    window.localStorage.setItem(key, clientId);
  } else {
    window.localStorage.removeItem(key);
  }
}

export function selectClientById(clients, clientId) {
  return clients.find((client) => client.id === clientId) || clients[0] || null;
}

export function ensureSelectedClientId(clients, selectedClientId) {
  if (selectedClientId && clients.some((client) => client.id === selectedClientId)) {
    return selectedClientId;
  }
  return clients[0]?.id || '';
}

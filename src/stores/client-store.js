import { createClientId } from '../core/ids.js';

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

export function normalizeBackendClient(client) {
  return {
    id: client.id,
    name: client.name,
    segment: client.segment || 'Клиент',
    directLogin: client.direct_login || 'Не подключен',
    metricaCounter: client.metrica_counter || 'Не подключен',
    yandexAccountId: client.yandex_account_id || '',
    targetCpa: client.target_cpa ?? '',
    mainGoalId: client.main_goal_id || '',
    conversionGoalIds: client.conversion_goal_ids || client.main_goal_id || '',
    notes: client.notes || '',
    lastSync: client.last_sync || '—',
    backend: true,
  };
}

export function createClientFromForm(name, directLogin, metricaCounter) {
  return {
    id: createClientId(name || 'client'),
    name,
    directLogin: directLogin || 'Не подключен',
    metricaCounter: metricaCounter || 'Не подключен',
    lastSync: '—',
    segment: 'Новый клиент',
  };
}

export function getCurrentClient(clients, selectedClientId) {
  return clients.find((client) => client.id === selectedClientId) || clients[0] || {};
}

export function createClientStore(storageKey) {
  function loadStoredClients() {
    try {
      const raw = window.localStorage.getItem(storageKey('directpilot_clients'));
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      return [];
    }
  }

  function saveStoredClients(clients) {
    try {
      window.localStorage.setItem(storageKey('directpilot_clients'), JSON.stringify(clients));
    } catch (error) {
      console.warn('Failed to persist clients locally', error);
    }
  }

  return {
    loadStoredClients,
    saveStoredClients,
    normalizeBackendClient,
    createClientFromForm,
    getCurrentClient,
  };
}

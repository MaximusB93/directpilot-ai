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
  const directLogin = client.directLogin ?? client.direct_login;
  const metricaCounter = client.metricaCounter ?? client.metrica_counter;
  const yandexAccountId = client.yandexAccountId ?? client.yandex_account_id;
  const targetCpa = client.targetCpa ?? client.target_cpa;
  const mainGoalId = client.mainGoalId ?? client.main_goal_id;
  const conversionGoalIds = client.conversionGoalIds ?? client.conversion_goal_ids;
  const lastSync = client.lastSync ?? client.last_sync;
  const syncStatus = client.syncStatus ?? client.sync_status;
  const syncError = client.syncError ?? client.sync_error;
  const lastSyncedAt = client.lastSyncedAt ?? client.last_synced_at;
  const syncVersion = client.syncVersion ?? client.sync_version;

  return {
    id: client.id,
    name: client.name,
    segment: client.segment || 'Клиент',
    directLogin: directLogin || 'Не подключен',
    metricaCounter: metricaCounter || 'Не подключен',
    yandexAccountId: yandexAccountId || '',
    targetCpa: targetCpa ?? '',
    mainGoalId: mainGoalId || '',
    conversionGoalIds: conversionGoalIds || mainGoalId || '',
    notes: client.notes || '',
    lastSync: lastSync || '—',
    syncStatus: syncStatus || 'never_synced',
    syncError: syncError || null,
    lastSyncedAt: lastSyncedAt || null,
    syncVersion: syncVersion || 0,
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

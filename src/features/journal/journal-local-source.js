import { scopedStorageKey } from '../../core/storage.js';
import {
  createJournalEntryPayload,
  createJournalQueryParams,
  filterJournalEntries,
  normalizeJournalEntries,
} from './journal-store.js';

export const JOURNAL_LOCAL_STORAGE_KEY = 'directpilot_journal_entries_v1';

function resolveStorage(storage) {
  if (storage) return storage;
  if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
  return null;
}

function safeParseEntries(raw) {
  try {
    return normalizeJournalEntries(JSON.parse(raw || '[]'));
  } catch {
    return [];
  }
}

function createDefaultId() {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `journal_${Date.now()}_${randomPart}`;
}

export function createJournalLocalSource({
  storage,
  storageKey = scopedStorageKey(JOURNAL_LOCAL_STORAGE_KEY),
  now = () => new Date().toISOString(),
  idFactory = createDefaultId,
} = {}) {
  const resolvedStorage = resolveStorage(storage);

  function readAll() {
    if (!resolvedStorage) return [];
    return safeParseEntries(resolvedStorage.getItem(storageKey));
  }

  function writeAll(entries) {
    if (!resolvedStorage) return normalizeJournalEntries(entries);
    const normalized = normalizeJournalEntries(entries);
    resolvedStorage.setItem(storageKey, JSON.stringify(normalized));
    return normalized;
  }

  function list(query = {}) {
    const params = createJournalQueryParams(query);
    const limit = Number(params.limit || 50);
    const cursor = Number(params.cursor || 0);
    const filtered = filterJournalEntries(readAll(), params);
    const items = filtered.slice(cursor, cursor + limit);
    const nextCursor = cursor + limit < filtered.length ? String(cursor + limit) : null;
    return { items, nextCursor };
  }

  function get(entryId) {
    const id = String(entryId || '').trim();
    if (!id) return null;
    return readAll().find((entry) => entry.id === id) || null;
  }

  function create(input = {}) {
    const entry = createJournalEntryPayload(input, { now: now(), id: input.id || idFactory(input) });
    writeAll([entry, ...readAll().filter((item) => item.id !== entry.id)]);
    return entry;
  }

  function replace(entries = []) {
    return writeAll(entries);
  }

  function clear() {
    if (resolvedStorage) resolvedStorage.removeItem(storageKey);
    return [];
  }

  return {
    storageKey,
    readAll,
    writeAll,
    list,
    get,
    create,
    replace,
    clear,
  };
}

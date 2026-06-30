const JOURNAL_SCOPES = ['client', 'account', 'system'];
const JOURNAL_SOURCES = ['ai', 'optimization', 'integration', 'sync', 'business_context', 'client', 'system'];
const JOURNAL_CATEGORIES = ['recommendation', 'action', 'status', 'data_change', 'error', 'note'];
const JOURNAL_SEVERITIES = ['info', 'success', 'warning', 'error'];
const JOURNAL_ACTOR_KINDS = ['user', 'ai', 'system', 'backend'];
const JOURNAL_ENTITY_KINDS = ['client', 'campaign', 'optimization_action', 'business_context', 'integration', 'sync_job', 'ai_recommendation'];

export const JOURNAL_DEFAULT_LIMIT = 50;

function firstAllowed(value, allowed, fallback) {
  const normalized = String(value || '').trim();
  return allowed.includes(normalized) ? normalized : fallback;
}

function cleanString(value, fallback = '') {
  const normalized = String(value ?? '').trim();
  return normalized || fallback;
}

function cleanNullableString(value) {
  const normalized = cleanString(value);
  return normalized || null;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function cleanObject(value) {
  return isPlainObject(value) ? { ...value } : {};
}

function normalizeDate(value, fallback = new Date().toISOString()) {
  const raw = cleanString(value);
  const parsed = raw ? new Date(raw) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed.toISOString() : fallback;
}

export function createInitialJournalState({ now = new Date().toISOString() } = {}) {
  return {
    items: [],
    filters: createDefaultJournalFilters(),
    loading: false,
    creating: false,
    error: '',
    nextCursor: null,
    loadedAt: now,
  };
}

export function createDefaultJournalFilters(overrides = {}) {
  return {
    clientId: cleanNullableString(overrides.clientId),
    scope: cleanString(overrides.scope),
    source: cleanString(overrides.source),
    category: cleanString(overrides.category),
    type: cleanString(overrides.type),
    severity: cleanString(overrides.severity),
    entityKind: cleanString(overrides.entityKind),
    entityId: cleanString(overrides.entityId),
    fromDate: cleanString(overrides.fromDate),
    toDate: cleanString(overrides.toDate),
    limit: normalizeLimit(overrides.limit),
    cursor: cleanNullableString(overrides.cursor),
  };
}

export function normalizeLimit(value, fallback = JOURNAL_DEFAULT_LIMIT) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(200, Math.max(1, Math.trunc(parsed)));
}

export function normalizeJournalActor(actor = {}) {
  const normalizedActor = isPlainObject(actor) ? actor : {};
  return {
    kind: firstAllowed(normalizedActor.kind, JOURNAL_ACTOR_KINDS, 'system'),
    id: cleanNullableString(normalizedActor.id),
    label: cleanString(normalizedActor.label, 'System'),
  };
}

export function normalizeJournalEntity(entity = null) {
  if (!isPlainObject(entity)) return null;
  const kind = firstAllowed(entity.kind, JOURNAL_ENTITY_KINDS, 'client');
  return {
    kind,
    id: cleanNullableString(entity.id),
    label: cleanString(entity.label, kind),
  };
}

export function normalizeJournalEntry(payload = {}, { now = new Date().toISOString() } = {}) {
  const entry = isPlainObject(payload) ? payload : {};
  const scope = firstAllowed(entry.scope, JOURNAL_SCOPES, entry.clientId ? 'client' : 'system');
  const clientId = scope === 'client' ? cleanNullableString(entry.clientId) : cleanNullableString(entry.clientId);
  const occurredAt = normalizeDate(entry.occurredAt, now);
  const createdAt = normalizeDate(entry.createdAt, occurredAt);
  const source = firstAllowed(entry.source, JOURNAL_SOURCES, 'system');
  const category = firstAllowed(entry.category, JOURNAL_CATEGORIES, 'note');
  const type = cleanString(entry.type, `${source}.${category}`);

  return {
    id: cleanString(entry.id, createJournalEntryId({ occurredAt, source, type, clientId })),
    scope,
    clientId,
    occurredAt,
    createdAt,
    source,
    category,
    type,
    severity: firstAllowed(entry.severity, JOURNAL_SEVERITIES, category === 'error' ? 'error' : 'info'),
    title: cleanString(entry.title, type),
    summary: cleanString(entry.summary, ''),
    actor: normalizeJournalActor(entry.actor),
    entity: normalizeJournalEntity(entry.entity),
    before: isPlainObject(entry.before) ? { ...entry.before } : null,
    after: isPlainObject(entry.after) ? { ...entry.after } : null,
    metadata: cleanObject(entry.metadata),
  };
}

export function normalizeJournalEntries(payload, options = {}) {
  const items = Array.isArray(payload) ? payload : Array.isArray(payload?.items) ? payload.items : [];
  return items.map((item) => normalizeJournalEntry(item, options)).sort(compareJournalEntriesNewestFirst);
}

export function createJournalEntryPayload(input = {}, { now = new Date().toISOString(), id = '' } = {}) {
  return normalizeJournalEntry({ ...input, id: id || input.id, createdAt: input.createdAt || now, occurredAt: input.occurredAt || now }, { now });
}

export function createJournalEntryId({ occurredAt = '', source = 'system', type = 'note', clientId = '' } = {}) {
  const raw = `${occurredAt}_${source}_${type}_${clientId}`.toLowerCase();
  const slug = raw.replace(/[^a-z0-9а-яё]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  return `journal_${slug || 'entry'}`;
}

export function createJournalQueryParams(filters = {}) {
  const normalized = createDefaultJournalFilters(filters);
  return Object.fromEntries(Object.entries(normalized).filter(([, value]) => value !== '' && value !== null && value !== undefined));
}

export function filterJournalEntries(entries = [], filters = {}) {
  const normalizedFilters = createDefaultJournalFilters(filters);
  const fromDate = parseFilterDate(normalizedFilters.fromDate);
  const toDate = parseFilterDate(normalizedFilters.toDate, true);

  return normalizeJournalEntries(entries).filter((entry) => {
    if (normalizedFilters.clientId && entry.clientId !== normalizedFilters.clientId) return false;
    if (normalizedFilters.scope && entry.scope !== normalizedFilters.scope) return false;
    if (normalizedFilters.source && entry.source !== normalizedFilters.source) return false;
    if (normalizedFilters.category && entry.category !== normalizedFilters.category) return false;
    if (normalizedFilters.type && entry.type !== normalizedFilters.type) return false;
    if (normalizedFilters.severity && entry.severity !== normalizedFilters.severity) return false;
    if (normalizedFilters.entityKind && entry.entity?.kind !== normalizedFilters.entityKind) return false;
    if (normalizedFilters.entityId && entry.entity?.id !== normalizedFilters.entityId) return false;

    const occurredAt = new Date(entry.occurredAt).getTime();
    if (fromDate && occurredAt < fromDate.getTime()) return false;
    if (toDate && occurredAt > toDate.getTime()) return false;
    return true;
  });
}

export function groupJournalEntriesByDate(entries = []) {
  const groups = new Map();
  normalizeJournalEntries(entries).forEach((entry) => {
    const dateKey = entry.occurredAt.slice(0, 10);
    if (!groups.has(dateKey)) {
      groups.set(dateKey, { date: dateKey, label: formatJournalEntryDate(entry.occurredAt), items: [] });
    }
    groups.get(dateKey).items.push(entry);
  });
  return [...groups.values()];
}

export function formatJournalEntryDate(value, locale = 'ru-RU') {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Без даты';
  return parsed.toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric' });
}

export function compareJournalEntriesNewestFirst(a, b) {
  return new Date(b.occurredAt).getTime() - new Date(a.occurredAt).getTime();
}

function parseFilterDate(value, endOfDay = false) {
  const raw = cleanString(value);
  if (!raw) return null;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return null;
  if (endOfDay && /^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    parsed.setHours(23, 59, 59, 999);
  }
  return parsed;
}

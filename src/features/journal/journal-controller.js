export async function loadJournalEntriesFlow({
  state,
  source,
  filters = state?.filters || {},
  onStart = () => {},
  onSuccess = () => {},
  onError = () => {},
  onFinally = () => {},
  render = () => {},
} = {}) {
  assertJournalState(state);
  assertJournalSource(source);

  onStart();
  state.loading = true;
  state.error = '';
  state.filters = { ...state.filters, ...filters };
  render();

  try {
    const response = await Promise.resolve(source.list(state.filters));
    state.items = Array.isArray(response?.items) ? response.items : [];
    state.nextCursor = response?.nextCursor || null;
    state.loadedAt = new Date().toISOString();
    onSuccess(response);
    return response;
  } catch (error) {
    state.error = error?.message || 'Не удалось загрузить журнал.';
    onError(error);
    return null;
  } finally {
    state.loading = false;
    onFinally();
    render();
  }
}

export async function loadMoreJournalEntriesFlow({
  state,
  source,
  onStart = () => {},
  onSuccess = () => {},
  onError = () => {},
  onFinally = () => {},
  render = () => {},
} = {}) {
  assertJournalState(state);
  assertJournalSource(source);
  if (!state.nextCursor) return null;

  onStart();
  state.loading = true;
  state.error = '';
  render();

  try {
    const response = await Promise.resolve(source.list({ ...state.filters, cursor: state.nextCursor }));
    const items = Array.isArray(response?.items) ? response.items : [];
    state.items = [...state.items, ...items];
    state.nextCursor = response?.nextCursor || null;
    state.loadedAt = new Date().toISOString();
    onSuccess(response);
    return response;
  } catch (error) {
    state.error = error?.message || 'Не удалось загрузить следующую страницу журнала.';
    onError(error);
    return null;
  } finally {
    state.loading = false;
    onFinally();
    render();
  }
}

export async function createJournalEntryFlow({
  state,
  source,
  input,
  onStart = () => {},
  onSuccess = () => {},
  onError = () => {},
  onFinally = () => {},
  render = () => {},
} = {}) {
  assertJournalState(state);
  assertJournalSource(source);

  onStart();
  state.creating = true;
  state.error = '';
  render();

  try {
    const entry = await Promise.resolve(source.create(input));
    state.items = [entry, ...state.items.filter((item) => item.id !== entry.id)];
    state.loadedAt = new Date().toISOString();
    onSuccess(entry);
    return entry;
  } catch (error) {
    state.error = error?.message || 'Не удалось создать запись журнала.';
    onError(error);
    return null;
  } finally {
    state.creating = false;
    onFinally();
    render();
  }
}

export async function refreshJournalFlow(options = {}) {
  return loadJournalEntriesFlow(options);
}

function assertJournalState(state) {
  if (!state || typeof state !== 'object') {
    throw new Error('Journal state is required');
  }
  if (!Array.isArray(state.items)) state.items = [];
  if (!state.filters || typeof state.filters !== 'object') state.filters = {};
}

function assertJournalSource(source) {
  if (!source || typeof source.list !== 'function' || typeof source.create !== 'function') {
    throw new Error('Journal source with list() and create() is required');
  }
}

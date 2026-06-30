function noop() {}

function closest(event, selector) {
  return event?.target?.closest?.(selector) || null;
}

function isJournalFilterField(event) {
  return Boolean(closest(event, '[data-journal-filters]') && event?.target?.name);
}

export function createJournalEventHandlers({
  state,
  readFilters = () => ({}),
  readCreateInput = () => ({}),
  loadEntries,
  loadMore,
  createEntry,
  refresh,
  resetFilters,
  render = noop,
} = {}) {
  if (!state) throw new Error('Journal state is required');
  if (typeof loadEntries !== 'function') throw new Error('Journal loadEntries dependency is required');
  if (typeof loadMore !== 'function') throw new Error('Journal loadMore dependency is required');
  if (typeof createEntry !== 'function') throw new Error('Journal createEntry dependency is required');
  if (typeof refresh !== 'function') throw new Error('Journal refresh dependency is required');
  if (typeof resetFilters !== 'function') throw new Error('Journal resetFilters dependency is required');

  function handleJournalChangeEvent(event) {
    if (!isJournalFilterField(event)) return;
    state.filters = {
      ...state.filters,
      [event.target.name]: event.target.value,
      cursor: null,
    };
    render();
  }

  async function handleJournalClickEvent(event) {
    if (closest(event, '[data-journal-apply-filters]')) {
      event.preventDefault();
      await loadEntries(readFilters(event));
      return;
    }

    if (closest(event, '[data-journal-reset-filters]')) {
      event.preventDefault();
      resetFilters();
      await loadEntries(state.filters);
      return;
    }

    if (closest(event, '[data-journal-refresh]')) {
      event.preventDefault();
      await refresh();
      return;
    }

    if (closest(event, '[data-journal-load-more]')) {
      event.preventDefault();
      await loadMore();
    }
  }

  async function handleJournalSubmitEvent(event) {
    const form = closest(event, '[data-journal-create-form]');
    if (!form) return;
    event.preventDefault();
    await createEntry(readCreateInput(event));
  }

  return {
    handleJournalClickEvent,
    handleJournalChangeEvent,
    handleJournalSubmitEvent,
  };
}

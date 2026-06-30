function isAuthenticationRequired(error) {
  return error?.message === 'Authentication required';
}

function noop() {}

export async function openWordstatFlow({
  state,
  ensureNav = noop,
  render = noop,
  loadConnection,
  readyMessage = 'Wordstat API готов. Можно загружать динамику.',
  notReadyMessage = 'Wordstat API не готов: проверьте YANDEX_SEARCH_API_KEY / YANDEX_SEARCH_FOLDER_ID или OAuth.',
} = {}) {
  if (!state) throw new Error('Wordstat state is required');
  if (typeof loadConnection !== 'function') throw new Error('Wordstat loadConnection dependency is required');

  state.active = true;
  state.status = 'Проверяем подключение Wordstat...';
  state.error = '';
  ensureNav();
  render();

  try {
    state.connection = await loadConnection();
    state.status = state.connection?.configured ? readyMessage : notReadyMessage;
  } catch (error) {
    if (isAuthenticationRequired(error)) return;
    state.connection = {
      configured: false,
      can_call_api: false,
      provider: 'yandex_search_api',
      message: error.message,
    };
    state.status = notReadyMessage;
  } finally {
    render();
  }
}

export async function submitWordstatDynamicsFlow({
  state,
  form,
  syncFormState,
  parsePhrases,
  loadDynamics,
  render = noop,
} = {}) {
  if (!state) throw new Error('Wordstat state is required');
  if (typeof syncFormState !== 'function') throw new Error('Wordstat syncFormState dependency is required');
  if (typeof parsePhrases !== 'function') throw new Error('Wordstat parsePhrases dependency is required');
  if (typeof loadDynamics !== 'function') throw new Error('Wordstat loadDynamics dependency is required');

  syncFormState(form);
  const phrases = parsePhrases(state.form.phrases);
  if (!phrases.length) {
    state.error = 'Добавьте хотя бы одну фразу.';
    render();
    return;
  }
  if (!state.form.fromDate || !state.form.toDate) {
    state.error = 'Укажите даты периода.';
    render();
    return;
  }

  state.loading = true;
  state.comparison = null;
  state.comparisonRange = null;
  state.status = `Отправляем batch-запрос: ${phrases.length} фраз.`;
  state.error = '';
  render();

  try {
    const payload = await loadDynamics();
    state.result = payload;
    state.status = `Готово: ${payload.meta?.completedPhrases || 0} фраз, ошибок: ${payload.meta?.failedPhrases || 0}.`;
  } catch (error) {
    if (isAuthenticationRequired(error)) return;
    state.error = error.message;
  } finally {
    state.loading = false;
    render();
  }
}

export async function compareWordstatPeriodFlow({
  state,
  loadDynamics,
  render = noop,
} = {}) {
  if (!state) throw new Error('Wordstat state is required');
  if (typeof loadDynamics !== 'function') throw new Error('Wordstat loadDynamics dependency is required');

  const fromDate = state.form.compareFromDate;
  const toDate = state.form.compareToDate;
  if (!fromDate || !toDate || !state.result) return;

  state.compareLoading = true;
  state.status = `Сравниваем с периодом: ${fromDate} → ${toDate}.`;
  state.error = '';
  render();

  try {
    state.comparison = await loadDynamics({ fromDate, toDate, forceRefresh: false });
    state.comparisonRange = { fromDate, toDate };
    state.status = 'Сравнение готово.';
  } catch (error) {
    if (isAuthenticationRequired(error)) return;
    state.error = error.message;
  } finally {
    state.compareLoading = false;
    render();
  }
}

export async function copyWordstatJsonFlow({
  state,
  copyText,
  render = noop,
} = {}) {
  if (!state) throw new Error('Wordstat state is required');
  if (typeof copyText !== 'function') throw new Error('Wordstat copyText dependency is required');

  await copyText(JSON.stringify({ current: state.result || {}, comparison: state.comparison || null }, null, 2));
  state.status = 'JSON результата скопирован.';
  render();
}

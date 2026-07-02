let fallbackClientsLoaded = false;

export async function loadClientsFromApiFlow({
  page,
  force = false,
  loading,
  loaded,
  businessContextLoading,
  clientsService,
  clientsStore,
  loadSelectedClientId,
  onStart,
  onSuccess,
  onFallback,
  onFinally,
}) {
  if (page !== 'app') return { status: 'skipped' };
  if (loading || ((loaded || fallbackClientsLoaded) && !force)) return { status: 'skipped' };

  onStart?.();

  try {
    const payload = await clientsService.fetchClients();
    const clients = payload.map(clientsStore.normalizeBackendClient);
    const storedSelected = loadSelectedClientId?.() || '';
    const selectedClientId = clients.find((client) => client.id === storedSelected)?.id || clients[0]?.id || '';
    const message = clients.length ? 'Клиенты загружены из базы данных.' : 'В базе пока нет клиентов. Создайте первого клиента.';
    fallbackClientsLoaded = false;
    onSuccess?.({ clients, selectedClientId, message, shouldResetBusinessContext: !businessContextLoading });
    return { status: 'success', clients, selectedClientId };
  } catch (error) {
    fallbackClientsLoaded = true;
    const storedClients = !loaded ? clientsStore.loadStoredClients() : [];
    const selectedClientId = storedClients.length
      ? storedClients.find((client) => client.id === loadSelectedClientId?.())?.id || storedClients[0]?.id || ''
      : undefined;
    const message = 'Backend недоступен, временно используем локальное хранилище.';
    onFallback?.({ clients: storedClients, selectedClientId, message, error });
    return { status: 'fallback', clients: storedClients, selectedClientId, error: message };
  } finally {
    onFinally?.();
  }
}

export function resetClientsFallbackLoadState() {
  fallbackClientsLoaded = false;
}

export async function createClientFlow({
  form,
  backendAvailable,
  clientsService,
  clientsStore,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  const formData = new FormData(form);
  const name = formData.get('name')?.toString().trim();
  const directLogin = formData.get('directLogin')?.toString().trim();
  const metricaCounter = formData.get('metricaCounter')?.toString().trim();

  if (!name) return { status: 'skipped' };

  const newClient = clientsStore.createClientFromForm(name, directLogin, metricaCounter);
  onStart?.('Сохраняем клиента...', newClient);

  try {
    if (backendAvailable) {
      const payload = await clientsService.createClient({
        id: newClient.id,
        name: newClient.name,
        directLogin: newClient.directLogin,
        metricaCounter: newClient.metricaCounter,
        segment: newClient.segment,
      });
      const client = clientsStore.normalizeBackendClient(payload);
      const message = 'Клиент сохранён в базе данных.';
      onSuccess?.({ client, selectedClientId: newClient.id, message, clearDraft: true });
      return { status: 'success', client, selectedClientId: newClient.id };
    }

    const message = 'Backend недоступен, клиент временно сохранён локально.';
    onSuccess?.({ client: newClient, selectedClientId: newClient.id, message, clearDraft: true });
    return { status: 'local', client: newClient, selectedClientId: newClient.id };
  } catch (error) {
    const message = `${error.message}. Клиент сохранён локально.`;
    onError?.({ client: newClient, selectedClientId: newClient.id, message, error });
    return { status: 'fallback', client: newClient, selectedClientId: newClient.id, error: message };
  } finally {
    onFinally?.();
  }
}

export function createClientSettingsDraftFromForm(form) {
  const formData = new FormData(form);
  return {
    name: formData.get('name')?.toString().trim() || '',
    directLogin: formData.get('directLogin')?.toString().trim() || '',
    metricaCounter: formData.get('metricaCounter')?.toString().trim() || '',
    targetCpa: formData.get('targetCpa')?.toString().trim() || '',
    mainGoalId: formData.get('mainGoalId')?.toString().trim() || '',
    conversionGoalIds: formData.get('conversionGoalIds')?.toString().trim() || '',
    notes: formData.get('notes')?.toString().trim() || '',
  };
}

export function createLocalClientSettingsUpdate(draft) {
  return {
    name: draft.name,
    directLogin: draft.directLogin || 'Не подключен',
    metricaCounter: draft.metricaCounter || 'Не подключен',
    targetCpa: draft.targetCpa,
    mainGoalId: draft.mainGoalId,
    conversionGoalIds: draft.conversionGoalIds,
    notes: draft.notes,
  };
}

export function createClientSettingsPayload(draft) {
  return {
    name: draft.name,
    direct_login: draft.directLogin || null,
    metrica_counter: draft.metricaCounter || null,
    target_cpa: draft.targetCpa ? Number(draft.targetCpa) : null,
    main_goal_id: draft.mainGoalId || null,
    conversion_goal_ids: draft.conversionGoalIds || null,
    notes: draft.notes || null,
  };
}

export async function saveClientSettingsFlow({
  selectedClientId,
  form,
  backendAvailable,
  clientsService,
  clientsStore,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId) return { status: 'skipped' };

  const draft = createClientSettingsDraftFromForm(form);
  const localUpdate = createLocalClientSettingsUpdate(draft);

  onStart?.({ draft, localUpdate, message: 'Сохраняем настройки клиента...' });

  try {
    if (backendAvailable) {
      const payload = await clientsService.updateClient(selectedClientId, createClientSettingsPayload(draft));
      const client = clientsStore.normalizeBackendClient(payload);
      const message = 'Настройки клиента сохранены в базе.';
      onSuccess?.({ client, localUpdate, message, backend: true });
      return { status: 'success', client };
    }

    const message = 'Backend недоступен, настройки сохранены локально.';
    onSuccess?.({ client: localUpdate, localUpdate, message, backend: false });
    return { status: 'local', client: localUpdate };
  } catch (error) {
    const message = `${error.message}. Локальная копия обновлена.`;
    onError?.({ localUpdate, message, error });
    return { status: 'fallback', error: message, localUpdate };
  } finally {
    onFinally?.();
  }
}

export async function deleteClientFlow({
  clientId,
  backendAvailable,
  clientsService,
  onConfirm,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!clientId) return { status: 'skipped' };
  if (onConfirm && !onConfirm()) return { status: 'cancelled' };

  onStart?.('Удаляем клиента...');

  try {
    if (backendAvailable) {
      await clientsService.deleteClient(clientId);
    }
    onSuccess?.({ clientId });
    return { status: 'success', clientId };
  } catch (error) {
    const message = error.message || 'Не удалось удалить клиента.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

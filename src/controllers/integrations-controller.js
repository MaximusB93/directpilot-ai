export async function loadIntegrationStatusFlow({
  integrationsService,
  onSuccess,
  onError,
  onFinally,
}) {
  try {
    const payload = await integrationsService.fetchYandexStatus();
    const status = {
      connected: Boolean(payload.connected),
      accounts: Array.isArray(payload.accounts) ? payload.accounts : [],
      message: payload.connected ? 'Яндекс подключён. Можно привязать аккаунт к клиенту.' : 'Яндекс ещё не подключён.',
    };
    onSuccess?.(status, payload);
    return { status: 'success', integrationStatus: status };
  } catch (error) {
    const status = {
      connected: false,
      accounts: [],
      message: 'Backend недоступен, статус Яндекса не проверен.',
    };
    onError?.(status, error);
    return { status: 'error', integrationStatus: status };
  } finally {
    onFinally?.();
  }
}

export async function startYandexOAuthFlow({
  integrationsService,
  onStart,
  onRedirect,
  onError,
}) {
  onStart?.('Запрашиваем OAuth URL...');

  try {
    const payload = await integrationsService.startYandexOAuth();
    onRedirect?.(payload.auth_url, payload);
    return { status: 'success', authUrl: payload.auth_url };
  } catch (error) {
    const message = error.message || 'Не удалось начать подключение Яндекса.';
    onError?.(message, error);
    return { status: 'error', error: message };
  }
}

export async function loadClientYandexIntegrationFlow({
  selectedClientId,
  loading,
  currentIntegration,
  force = false,
  integrationsService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || loading || (currentIntegration && !force)) return { status: 'skipped' };

  onStart?.('Загружаем привязку клиента к Яндексу...');

  try {
    const payload = await integrationsService.fetchClientYandexIntegration(selectedClientId);
    const selectedAccount = payload.bound_account || payload.selected_account || payload.boundAccount || payload.selectedAccount || null;
    const selectedAccountId = selectedAccount?.id || '';
    const message = selectedAccount ? 'Аккаунт Яндекса привязан к клиенту.' : 'Выберите аккаунт Яндекса для клиента.';
    onSuccess?.({ payload, selectedAccountId, message });
    return { status: 'success', integration: payload, selectedAccountId };
  } catch (error) {
    const message = error.message || 'Не удалось загрузить привязку Яндекса.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function bindClientYandexAccountFlow({
  selectedClientId,
  accountId,
  integrationsService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId || !accountId) return { status: 'skipped' };

  onStart?.('Привязываем аккаунт Яндекса к клиенту...');

  try {
    await integrationsService.bindClientYandexIntegration(selectedClientId, accountId);
    const payload = await integrationsService.fetchClientYandexIntegration(selectedClientId);
    const selectedAccount = payload.bound_account || payload.selected_account || payload.boundAccount || payload.selectedAccount || null;
    const selectedAccountId = selectedAccount?.id || accountId;
    onSuccess?.({ payload, accountId: selectedAccountId, message: 'Аккаунт Яндекса привязан к клиенту.' });
    return { status: 'success', integration: payload, accountId: selectedAccountId };
  } catch (error) {
    const message = error.message || 'Не удалось привязать аккаунт.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

export async function unbindClientYandexAccountFlow({
  selectedClientId,
  integrationsService,
  onStart,
  onSuccess,
  onError,
  onFinally,
}) {
  if (!selectedClientId) return { status: 'skipped' };

  onStart?.('Отвязываем аккаунт Яндекса...');

  try {
    await integrationsService.unbindClientYandexIntegration(selectedClientId);
    const payload = await integrationsService.fetchClientYandexIntegration(selectedClientId);
    onSuccess?.({ payload, message: 'Аккаунт отвязан от клиента.' });
    return { status: 'success', integration: payload };
  } catch (error) {
    const message = error.message || 'Не удалось отвязать аккаунт.';
    onError?.(message, error);
    return { status: 'error', error: message };
  } finally {
    onFinally?.();
  }
}

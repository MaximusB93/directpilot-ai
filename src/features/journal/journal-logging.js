function clientEntity(client = {}) {
  return {
    kind: 'client',
    id: client.id || null,
    label: client.name || 'Клиент',
  };
}

function safeClientId(client = {}) {
  return client.id || null;
}

function safeClientName(client = {}) {
  return client.name || 'Клиент';
}

function cleanMetadata(metadata = {}) {
  return metadata && typeof metadata === 'object' && !Array.isArray(metadata) ? { ...metadata } : {};
}

export function createClientSelectedJournalEvent({ client = {}, actor = {}, metadata = {} } = {}) {
  return {
    scope: 'client',
    clientId: safeClientId(client),
    source: 'client',
    category: 'status',
    type: 'client.selected',
    severity: 'info',
    title: 'Выбран клиент',
    summary: `Активный клиент: ${safeClientName(client)}.`,
    actor,
    entity: clientEntity(client),
    metadata: cleanMetadata(metadata),
  };
}

export function createClientCreatedJournalEvent({ client = {}, actor = {}, metadata = {} } = {}) {
  return {
    scope: 'client',
    clientId: safeClientId(client),
    source: 'client',
    category: 'data_change',
    type: 'client.created',
    severity: 'success',
    title: 'Создан клиент',
    summary: `Создана карточка клиента ${safeClientName(client)}.`,
    actor,
    entity: clientEntity(client),
    after: {
      id: client.id || null,
      name: client.name || '',
      directLogin: client.directLogin || '',
      metricaCounter: client.metricaCounter || '',
    },
    metadata: cleanMetadata(metadata),
  };
}

export function createClientUpdatedJournalEvent({ client = {}, actor = {}, metadata = {} } = {}) {
  return {
    scope: 'client',
    clientId: safeClientId(client),
    source: 'client',
    category: 'data_change',
    type: 'client.updated',
    severity: 'info',
    title: 'Обновлены настройки клиента',
    summary: `Обновлена карточка клиента ${safeClientName(client)}.`,
    actor,
    entity: clientEntity(client),
    after: {
      id: client.id || null,
      name: client.name || '',
      directLogin: client.directLogin || '',
      metricaCounter: client.metricaCounter || '',
      mainGoalId: client.mainGoalId || '',
      conversionGoalIds: client.conversionGoalIds || '',
    },
    metadata: cleanMetadata(metadata),
  };
}

export function createOptimizationActionStatusJournalEvent({
  action = {},
  status = action.status,
  actor = {},
  metadata = {},
} = {}) {
  const actionId = action.id || action.action_id || null;
  const actionTitle = action.title || action.name || actionId || 'Действие оптимизации';
  const normalizedStatus = status || 'updated';
  return {
    scope: 'client',
    clientId: action.clientId || action.client_id || null,
    source: 'optimization',
    category: 'action',
    type: 'optimization.action_status_changed',
    severity: normalizedStatus === 'rejected' ? 'warning' : 'success',
    title: 'Изменён статус действия оптимизации',
    summary: `Статус «${actionTitle}» изменён на ${normalizedStatus}.`,
    actor,
    entity: {
      kind: 'optimization_action',
      id: actionId,
      label: actionTitle,
    },
    after: {
      status: normalizedStatus,
    },
    metadata: cleanMetadata(metadata),
  };
}

export function createSyncStatusJournalEvent({
  status = 'started',
  client = {},
  actor = {},
  entityId = null,
  severity = '',
  metadata = {},
} = {}) {
  const isFailed = status === 'failed' || severity === 'error';
  const normalizedStatus = isFailed ? 'failed' : status || 'started';
  return {
    scope: 'client',
    clientId: safeClientId(client),
    source: 'sync',
    category: isFailed ? 'error' : 'status',
    type: `sync.${normalizedStatus}`,
    severity: isFailed ? 'error' : normalizedStatus === 'completed' ? 'success' : 'info',
    title: isFailed ? 'Ошибка синхронизации' : 'Синхронизация данных',
    summary: isFailed
      ? `Синхронизация клиента ${safeClientName(client)} завершилась ошибкой.`
      : `Синхронизация клиента ${safeClientName(client)}: ${normalizedStatus}.`,
    actor,
    entity: {
      kind: 'sync_job',
      id: entityId,
      label: `Sync ${normalizedStatus}`,
    },
    metadata: cleanMetadata(metadata),
  };
}

export function createIntegrationStatusJournalEvent({
  action = 'updated',
  client = {},
  actor = {},
  entityId = null,
  metadata = {},
} = {}) {
  const isBound = action === 'bound';
  const isUnbound = action === 'unbound';
  return {
    scope: 'client',
    clientId: safeClientId(client),
    source: 'integration',
    category: 'status',
    type: isBound ? 'integration.yandex_account_bound' : isUnbound ? 'integration.yandex_account_unbound' : 'integration.yandex_updated',
    severity: isBound ? 'success' : 'info',
    title: isBound ? 'Привязан аккаунт Яндекса' : isUnbound ? 'Аккаунт Яндекса отвязан' : 'Интеграция обновлена',
    summary: isBound
      ? `К клиенту ${safeClientName(client)} привязан аккаунт Яндекса.`
      : isUnbound
        ? `От клиента ${safeClientName(client)} отвязан аккаунт Яндекса.`
        : `Интеграция клиента ${safeClientName(client)} обновлена.`,
    actor,
    entity: {
      kind: 'integration',
      id: entityId,
      label: 'Yandex Direct',
    },
    metadata: cleanMetadata(metadata),
  };
}

export const CLIENTS_PAGE_ID = 'clients';

export const clientsPage = {
  id: CLIENTS_PAGE_ID,
  title: 'Клиенты',
  description: 'Карточки клиентов, выбранный клиент, настройки Direct login, Метрики и целей.',
};

export function clientsPageContract() {
  return {
    routeId: CLIENTS_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'accountClients',
      'backendClientsAvailable',
      'backendClientsStatus',
      'clientFormStatus',
      'clientDraftName',
      'clientDraftDirectLogin',
      'clientDraftMetricaCounter',
      'selectedClient',
      'clientSettingsDraft',
      'clientSettingsSaving',
      'clientSettingsStatus',
    ],
    legacyRenderer: 'renderClients',
    extractionStatus: 'content-composer-ready',
    extractedBuilders: [
      'renderClientsIntro',
      'renderClientCreatePanel',
      'renderClientSettingsPanel',
      'renderClientGrid',
      'renderClientsContent',
    ],
    nextStep: 'Wire src/main.js renderClients to renderClientsContent in one controlled patch.',
  };
}

export function renderClientsIntro() {
  return `
    <div class="pageIntro"><span class="eyebrow">👥 Клиенты</span><h2>Клиенты как отдельные сущности</h2><p>Создайте отдельную карточку клиента для каждого аккаунта/проекта и укажите логин Яндекс.Директа и счётчик Метрики.</p></div>
  `;
}

export function renderClientCreatePanel({
  clientDraftName,
  clientDraftDirectLogin,
  clientDraftMetricaCounter,
  backendClientsStatus,
  clientFormStatus,
  escapeHtml,
}) {
  return `
    <section class="panel clientConnectPanel">
      <div>
        <h3>Добавить клиента</h3>
        <p>Создайте отдельную карточку под каждый рекламный аккаунт или проект.</p>
      </div>
      <form class="clientConnectForm" data-client-form>
        <input name="name" value="${escapeHtml(clientDraftName)}" placeholder="Название клиента" autocomplete="organization" required />
        <input name="directLogin" value="${escapeHtml(clientDraftDirectLogin)}" placeholder="Логин Яндекс.Директа" autocomplete="off" />
        <input name="metricaCounter" value="${escapeHtml(clientDraftMetricaCounter)}" placeholder="ID счётчика Метрики" inputmode="numeric" autocomplete="off" />
        <button class="approveButton" type="submit">Добавить клиента</button>
      </form>
      <details class="quietDetails">
        <summary>Технический статус хранения</summary>
        <div class="authStatus integrationStatus">${escapeHtml(backendClientsStatus)}</div>
      </details>
      ${clientFormStatus ? `<div class="authStatus integrationStatus">${escapeHtml(clientFormStatus)}</div>` : ''}
    </section>
  `;
}

export function renderClientSettingsPanel({
  selectedClient,
  clientSettingsDraft,
  clientSettingsSaving,
  clientSettingsStatus,
  escapeHtml,
}) {
  if (!selectedClient?.id) return '';

  return `
    <section class="panel clientConnectPanel">
      <div>
        <h3>Настройки клиента «${escapeHtml(selectedClient.name)}»</h3>
        <p>Настройки относятся только к выбранному клиенту. Привязка Яндекса настраивается отдельно во вкладке интеграций.</p>
      </div>
      <form class="clientSettingsForm" data-client-settings-form>
        <div class="settingsGrid">
          <label>Название<input name="name" value="${escapeHtml(clientSettingsDraft?.name ?? selectedClient.name ?? '')}" required /></label>
          <label>Логин Директа<input name="directLogin" value="${escapeHtml(clientSettingsDraft?.directLogin ?? selectedClient.directLogin ?? '')}" /></label>
          <label>ID счётчика Метрики<input name="metricaCounter" value="${escapeHtml(clientSettingsDraft?.metricaCounter ?? selectedClient.metricaCounter ?? '')}" /></label>
          <label>Целевой CPA<input name="targetCpa" value="${escapeHtml(String(clientSettingsDraft?.targetCpa ?? selectedClient.targetCpa ?? ''))}" inputmode="numeric" /></label>
          <label>Основная цель<input name="mainGoalId" value="${escapeHtml(clientSettingsDraft?.mainGoalId ?? selectedClient.mainGoalId ?? '')}" /></label>
          <label>Цели конверсий<input name="conversionGoalIds" value="${escapeHtml(clientSettingsDraft?.conversionGoalIds ?? selectedClient.conversionGoalIds ?? '')}" placeholder="12345,67890" /></label>
        </div>
        <label class="fullWidthLabel">Заметки<textarea name="notes" placeholder="Что важно знать AI о клиенте">${escapeHtml(clientSettingsDraft?.notes ?? selectedClient.notes ?? '')}</textarea></label>
        <div class="heroActions">
          <button class="approveButton" type="submit" ${clientSettingsSaving ? 'disabled' : ''}>${clientSettingsSaving ? 'Сохраняем...' : 'Сохранить настройки'}</button>
          <button class="secondaryButton" type="button" data-reset-client-settings>Сбросить</button>
          <button class="dangerButton" type="button" data-delete-client="${escapeHtml(selectedClient.id)}">Удалить клиента</button>
        </div>
      </form>
      ${clientSettingsStatus ? `<div class="authStatus integrationStatus">${escapeHtml(clientSettingsStatus)}</div>` : ''}
    </section>
  `;
}

export function renderClientGrid({ accountClients, selectedClientId, escapeHtml }) {
  if (!accountClients.length) {
    return `
      <section class="panel emptyStatePanel">
        <h3>Клиентов пока нет</h3>
        <p>Добавьте первого клиента выше. После этого появятся настройки Direct, Метрики, целей и интеграций.</p>
      </section>
    `;
  }

  return `
    <div class="clientGrid">${accountClients.map((client) => `<article class="clientCard ${client.id === selectedClientId ? 'selected' : ''}"><span>${escapeHtml(client.segment || 'Клиент')}</span><h3>${escapeHtml(client.name)}</h3><p>Direct: ${escapeHtml(client.directLogin || 'Не подключен')}</p><p>Метрика: ${escapeHtml(client.metricaCounter || 'Не подключен')}</p><button data-select-client="${escapeHtml(client.id)}">${client.id === selectedClientId ? 'Выбран' : 'Выбрать'}</button></article>`).join('')}</div>
  `;
}

export function renderClientsContent(context) {
  return `
    ${renderClientsIntro(context)}
    ${renderClientCreatePanel(context)}
    ${renderClientSettingsPanel(context)}
    ${renderClientGrid(context)}
  `;
}

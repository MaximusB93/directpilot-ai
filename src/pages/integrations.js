export const INTEGRATIONS_PAGE_ID = 'integrations';

export const integrationsPage = {
  id: INTEGRATIONS_PAGE_ID,
  title: 'Интеграции',
  description: 'Подключение Яндекса, доступные аккаунты и привязка аккаунта к клиенту.',
};

export function integrationsPageContract() {
  return {
    routeId: INTEGRATIONS_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
      'integrationStatus',
      'clientYandexIntegration',
      'clientYandexStatus',
      'clientYandexLoading',
      'apiBaseDraft',
    ],
    legacyRenderer: 'renderIntegrations',
    extractionStatus: 'content-composer-ready',
    extractedBuilders: [
      'renderIntegrationsIntro',
      'renderYandexConnectPanel',
      'renderClientYandexAccountPanel',
      'renderIntegrationsContent',
    ],
    nextStep: 'Move optimization page markup after integrations wiring is stable.',
  };
}

export function renderIntegrationsIntro({ escapeHtml }) {
  return `
    <div class="pageIntro">
      <span class="eyebrow">Интеграции</span>
      <h2>Подключите Яндекс.Директ и Метрику</h2>
      <p>${escapeHtml('Подключение хранится в backend. После подключения выберите аккаунт Яндекса для активного клиента.')}</p>
    </div>
  `;
}

export function renderYandexConnectPanel({ integrationStatus = {}, escapeHtml }) {
  const accounts = integrationStatus.accounts || [];
  return `
    <section class="panel integrationConnectPanel">
      <div class="panelHeader"><div><h3>Яндекс</h3><p>Доступ нужен для синхронизации кампаний, расходов, целей и поисковых запросов.</p></div><button class="approveButton" data-integration="yandex-direct">Подключить Яндекс</button></div>
      <div class="authStatus integrationStatus">${escapeHtml(integrationStatus.message || 'Статус подключения ещё не проверен.')}</div>
      ${integrationStatus.connected ? `<div class="integrationSuccess">Подключено аккаунтов: ${accounts.length}</div>` : ''}
    </section>
  `;
}

export function renderClientYandexAccountPanel({
  selectedClient = {},
  integrationStatus = {},
  clientYandexIntegration = null,
  clientYandexStatus = '',
  clientYandexLoading = false,
  escapeHtml,
}) {
  const accounts = integrationStatus.accounts || [];
  const selectedAccountId = String(clientYandexIntegration?.selected_account?.id || selectedClient.yandexAccountId || '');
  const accountCards = accounts.map((account) => {
    const accountId = String(account.id || '');
    const selected = accountId === selectedAccountId;
    const buttonClass = selected ? 'secondaryButton' : 'approveButton';
    const buttonText = selected ? 'Привязан' : 'Привязать';
    return `<article class="accountCard ${selected ? 'selected' : ''}"><div><strong>${escapeHtml(account.login || account.name || account.id)}</strong><span>${escapeHtml(account.id)}</span></div><button class="${buttonClass}" data-bind-yandex-account="${escapeHtml(account.id)}" ${selected ? 'disabled' : ''}>${buttonText}</button></article>`;
  }).join('');

  return `
    <section class="panel integrationConnectPanel">
      <div class="panelHeader"><div><h3>Привязка к клиенту</h3><p>Активный клиент: ${escapeHtml(selectedClient.name || 'не выбран')}. Direct login: ${escapeHtml(selectedClient.directLogin || 'не указан')}.</p></div><button class="secondaryButton" data-refresh-client-yandex ${selectedClient.id ? '' : 'disabled'}>Обновить</button></div>
      ${clientYandexStatus ? `<div class="authStatus integrationStatus">${escapeHtml(clientYandexStatus)}</div>` : ''}
      ${clientYandexLoading ? '<div class="authStatus integrationStatus">Загружаем доступные аккаунты...</div>' : ''}
      ${accounts.length ? `<div class="accountList">${accountCards}</div>` : '<div class="authStatus integrationStatus">Нет доступных аккаунтов. Сначала подключите Яндекс.</div>'}
      ${clientYandexIntegration?.selected_account ? `<button class="dangerButton" data-unbind-yandex ${selectedClient.id ? '' : 'disabled'}>Отвязать аккаунт</button>` : ''}
    </section>
  `;
}

export function renderIntegrationsContent(context) {
  return `
    ${renderIntegrationsIntro(context)}
    ${renderYandexConnectPanel(context)}
    ${renderClientYandexAccountPanel(context)}
  `;
}

import { renderEmptyState, renderPanel, renderStatusBadge } from '../components/index.js';

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
    componentPrimitives: [
      'renderPanel',
      'renderEmptyState',
      'renderStatusBadge',
    ],
    extractedBuilders: [
      'renderIntegrationsIntro',
      'renderIntegrationStatusMessage',
      'renderYandexConnectPanel',
      'renderClientYandexAccountPanel',
      'renderIntegrationsContent',
    ],
    nextStep: 'Use UI primitives in one more page after integrations wiring is stable.',
  };
}

function integrationConnectionTone(integrationStatus = {}) {
  if (integrationStatus.connected) return 'success';
  if (integrationStatus.message) return 'warning';
  return 'neutral';
}

function renderIntegrationStatusMessage(message, { escapeHtml, className = 'integrationStatus' } = {}) {
  if (!message) return '';
  return `<div class="authStatus ${escapeHtml(className)}">${escapeHtml(message)}</div>`;
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
  const statusMessage = integrationStatus.message || 'Статус подключения ещё не проверен.';
  const connectionBadge = renderStatusBadge({
    label: integrationStatus.connected ? 'Подключено' : 'Не готово',
    tone: integrationConnectionTone(integrationStatus),
    title: statusMessage,
  });

  return renderPanel({
    title: 'Яндекс',
    subtitle: 'Доступ нужен для синхронизации кампаний, расходов, целей и поисковых запросов.',
    className: 'integrationConnectPanel',
    actions: `<div class="panelActionsInline">${connectionBadge}<button class="approveButton" data-integration="yandex-direct">Подключить Яндекс</button></div>`,
    children: `
      ${renderIntegrationStatusMessage(statusMessage, { escapeHtml })}
      ${integrationStatus.connected ? `<div class="integrationSuccess">Подключено аккаунтов: ${accounts.length}</div>` : ''}
    `,
  });
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
  const boundAccount = clientYandexIntegration?.bound_account
    || clientYandexIntegration?.selected_account
    || clientYandexIntegration?.boundAccount
    || clientYandexIntegration?.selectedAccount
    || null;
  const selectedAccountId = String(boundAccount?.id || selectedClient.yandexAccountId || '');
  const selectedAccountBadge = renderStatusBadge({
    label: selectedAccountId ? 'Аккаунт привязан' : 'Аккаунт не выбран',
    tone: selectedAccountId ? 'success' : 'warning',
    title: selectedAccountId || 'Для активного клиента не выбран аккаунт Яндекса',
  });
  const accountCards = accounts.map((account) => {
    const accountId = String(account.id || '');
    const selected = accountId === selectedAccountId;
    const buttonClass = selected ? 'secondaryButton' : 'approveButton';
    const buttonText = selected ? 'Привязан' : 'Привязать';
    const selectedBadge = selected ? renderStatusBadge({ label: 'выбран', tone: 'success' }) : '';
    return `<article class="accountCard ${selected ? 'selected' : ''}"><div><strong>${escapeHtml(account.login || account.name || account.id)}</strong><span>${escapeHtml(account.id)}</span>${selectedBadge}</div><div class="panelActionsInline"><button class="${buttonClass}" data-bind-yandex-account="${escapeHtml(account.id)}" ${selected ? 'disabled' : ''}>${buttonText}</button><button class="dangerButton" data-delete-yandex-account="${escapeHtml(account.id)}">Удалить</button></div></article>`;
  }).join('');

  return renderPanel({
    title: 'Привязка к клиенту',
    subtitle: `Активный клиент: ${selectedClient.name || 'не выбран'}. Direct login: ${selectedClient.directLogin || 'не указан'}.`,
    className: 'integrationConnectPanel',
    actions: `<div class="panelActionsInline">${selectedAccountBadge}<button class="secondaryButton" data-refresh-client-yandex ${selectedClient.id ? '' : 'disabled'}>Обновить</button></div>`,
    children: `
      ${renderIntegrationStatusMessage(clientYandexStatus, { escapeHtml })}
      ${clientYandexLoading ? renderIntegrationStatusMessage('Загружаем доступные аккаунты...', { escapeHtml }) : ''}
      ${accounts.length ? `<div class="accountList">${accountCards}</div>` : renderEmptyState({ title: 'Нет доступных аккаунтов', description: 'Сначала подключите Яндекс, затем выберите аккаунт для активного клиента.' })}
      ${boundAccount ? `<button class="dangerButton" data-unbind-yandex ${selectedClient.id ? '' : 'disabled'}>Отвязать аккаунт</button>` : ''}
    `,
  });
}

export function renderIntegrationsContent(context) {
  return `
    ${renderIntegrationsIntro(context)}
    ${renderYandexConnectPanel(context)}
    ${renderClientYandexAccountPanel(context)}
  `;
}

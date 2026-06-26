export const CLIENTS_PAGE_ID = 'clients';

export const clientsPage = {
  id: CLIENTS_PAGE_ID,
  title: 'Клиенты',
  description: 'Карточки клиентов, выбранный клиент, настройки Direct login, Метрики, целей и fallback-режим.',
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
      'performanceSummary',
    ],
    legacyRenderer: 'renderClients',
    extractionStatus: 'contract-only',
    nextStep: 'Move renderClients markup from src/main.js after dashboard wiring is stable.',
  };
}

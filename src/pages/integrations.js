export const INTEGRATIONS_PAGE_ID = 'integrations';

export const integrationsPage = {
  id: INTEGRATIONS_PAGE_ID,
  title: 'Интеграции',
  description: 'OAuth Яндекса, доступные аккаунты, привязка аккаунта к клиенту и backend API URL.',
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
    extractionStatus: 'contract-only',
    nextStep: 'Move renderIntegrations markup and Yandex integration actions after service layer is wired.',
  };
}

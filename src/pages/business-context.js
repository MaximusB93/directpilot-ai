export const BUSINESS_CONTEXT_PAGE_ID = 'business-context';

export const businessContextPage = {
  id: BUSINESS_CONTEXT_PAGE_ID,
  title: 'Контекст бизнеса',
  description: 'Память проекта: ниша, продукт, аудитория, география, офферы, ограничения и заметки AI.',
};

export function businessContextPageContract() {
  return {
    routeId: BUSINESS_CONTEXT_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
      'businessContext',
      'businessContextLoading',
      'businessContextStatus',
    ],
    legacyRenderer: 'renderBusinessContext',
    extractionStatus: 'contract-only',
    nextStep: 'Move renderBusinessContext and renderBusinessContextPanel after dashboard and clients page wiring are stable.',
  };
}

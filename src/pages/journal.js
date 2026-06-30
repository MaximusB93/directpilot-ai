import { createJournalPageRenderers } from '../features/journal/journal-page.js';

export const JOURNAL_PAGE_ID = 'journal';

export const journalPage = {
  id: JOURNAL_PAGE_ID,
  title: 'Журнал',
  description: 'История важных событий по выбранному клиенту.',
};

export function journalPageContract() {
  return {
    routeId: JOURNAL_PAGE_ID,
    requiredContext: ['selectedClientId', 'selectedClient', 'journalState'],
    extractionStatus: 'registered-with-page-renderer',
    nextStep: 'Wire Journal runtime in app shell and client-scope reset before switching route mode to module.',
  };
}

export function renderJournalContent({ selectedClient, selectedClientId, journalState, escapeHtml }) {
  const { renderJournalPage } = createJournalPageRenderers({ escapeHtml });
  return renderJournalPage({
    selectedClient,
    selectedClientId,
    state: journalState,
  });
}

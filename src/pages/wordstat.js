export const WORDSTAT_PAGE_ID = 'wordstat';

export const wordstatPage = {
  id: WORDSTAT_PAGE_ID,
  title: 'Wordstat',
  description: 'Динамика спроса по ключевым фразам, регионам, периодам и устройствам.',
};

export function wordstatPageContract() {
  return {
    routeId: WORDSTAT_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
    ],
    legacyRenderer: 'renderWordstatPage',
    extractionStatus: 'registered-with-legacy-shell',
    extractedBuilders: [
      'createWordstatPageRenderers',
      'createWordstatEventHandlers',
      'renderWordstatContent',
    ],
    nextStep: 'Remove standalone Wordstat scripts from app.html after module mount owns the full lifecycle.',
  };
}

export function renderWordstatContent({ selectedClient, escapeHtml }) {
  const clientName = selectedClient?.name || 'Клиент не выбран';
  return `
    <section class="wordstatModuleShell" data-wordstat-module-shell>
      <div class="workspace" data-wordstat-workspace>
        <div class="pageIntro">
          <span class="eyebrow">📈 Wordstat</span>
          <h2>Готовим модуль спроса</h2>
          <p>Wordstat загружается для клиента «${escapeHtml(clientName)}». Если данные не появились автоматически, обновите страницу или проверьте подключение.</p>
        </div>
      </div>
    </section>
  `;
}

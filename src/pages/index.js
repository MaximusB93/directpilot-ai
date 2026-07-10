import {
  DASHBOARD_PAGE_ID,
  dashboardPage,
  dashboardPageContract,
  renderDashboardContent,
  renderDashboardPage,
} from './dashboard.js';
import {
  CLIENTS_PAGE_ID,
  clientsPage,
  clientsPageContract,
  renderClientsContent,
} from './clients.js';
import {
  BUSINESS_CONTEXT_PAGE_ID,
  businessContextPage,
  businessContextPageContract,
  renderBusinessContextContent,
} from './business-context.js';
import {
  INTEGRATIONS_PAGE_ID,
  integrationsPage,
  integrationsPageContract,
  renderIntegrationsContent,
} from './integrations.js';
import {
  AI_ASSISTANT_PAGE_ID,
  aiAssistantPage,
  aiAssistantPageContract,
  renderAiAssistantContent,
} from './ai-assistant.js';
import {
  OPTIMIZATION_PAGE_ID,
  optimizationPage,
  optimizationPageContract,
  renderOptimizationContent,
} from './optimization.js';
import {
  WORDSTAT_PAGE_ID,
  wordstatPage,
  wordstatPageContract,
  renderWordstatContent,
} from './wordstat.js';
import {
  JOURNAL_PAGE_ID,
  journalPage,
  journalPageContract,
  renderJournalContent,
} from './journal.js';
import {
  SETTINGS_PAGE_ID,
  settingsPage,
  settingsPageContract,
  renderSettingsContent,
} from './settings.js';

export const APP_PAGES = {
  [DASHBOARD_PAGE_ID]: dashboardPage,
  [CLIENTS_PAGE_ID]: clientsPage,
  [BUSINESS_CONTEXT_PAGE_ID]: businessContextPage,
  [INTEGRATIONS_PAGE_ID]: integrationsPage,
  [AI_ASSISTANT_PAGE_ID]: aiAssistantPage,
  [OPTIMIZATION_PAGE_ID]: optimizationPage,
  [WORDSTAT_PAGE_ID]: wordstatPage,
  [JOURNAL_PAGE_ID]: journalPage,
  [SETTINGS_PAGE_ID]: settingsPage,
};

export const PAGE_CONTRACTS = {
  [DASHBOARD_PAGE_ID]: dashboardPageContract(),
  [CLIENTS_PAGE_ID]: clientsPageContract(),
  [BUSINESS_CONTEXT_PAGE_ID]: businessContextPageContract(),
  [INTEGRATIONS_PAGE_ID]: integrationsPageContract(),
  [AI_ASSISTANT_PAGE_ID]: aiAssistantPageContract(),
  [OPTIMIZATION_PAGE_ID]: optimizationPageContract(),
  [WORDSTAT_PAGE_ID]: wordstatPageContract(),
  [JOURNAL_PAGE_ID]: journalPageContract(),
  [SETTINGS_PAGE_ID]: settingsPageContract(),
};

export const PAGE_RENDERERS = {
  [DASHBOARD_PAGE_ID]: renderDashboardPage,
};

export const PAGE_CONTENT_RENDERERS = {
  [DASHBOARD_PAGE_ID]: renderDashboardContent,
  [CLIENTS_PAGE_ID]: renderClientsContent,
  [BUSINESS_CONTEXT_PAGE_ID]: renderBusinessContextContent,
  [INTEGRATIONS_PAGE_ID]: renderIntegrationsContent,
  [AI_ASSISTANT_PAGE_ID]: renderAiAssistantContent,
  [OPTIMIZATION_PAGE_ID]: renderOptimizationContent,
  [WORDSTAT_PAGE_ID]: renderWordstatContent,
  [JOURNAL_PAGE_ID]: renderJournalContent,
  [SETTINGS_PAGE_ID]: renderSettingsContent,
};

export function getPageByRouteId(routeId) {
  return APP_PAGES[routeId] || null;
}

export function getPageContract(routeId) {
  return PAGE_CONTRACTS[routeId] || null;
}

export function getPageRenderer(routeId) {
  return PAGE_RENDERERS[routeId] || null;
}

export function getPageContentRenderer(routeId) {
  return PAGE_CONTENT_RENDERERS[routeId] || null;
}

export function listRegisteredPages() {
  return Object.values(APP_PAGES);
}

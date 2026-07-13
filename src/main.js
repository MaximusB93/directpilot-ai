import {
  API_BASE,
  escapeHtml,
  saveApiBase,
} from './core/api.js';
import {
  clearSession,
  getCurrentEmail,
  getSessionToken,
  saveSession,
  scopedStorageKey,
} from './core/storage.js';
import { requestEmailCode, verifyEmailCode } from './core/session-api.js';
import { resolvePageContentRenderer, resolvePageRenderer } from './app/page-router.js';
import { normalizeAppRouteId } from './app/routes.js';
import { applyClientScopeResetPatch, createClientScopeResetPatch } from './app/client-scope-reset.js';
import './wordstat.js';
import {
  createDefaultJournalFilters,
  createInitialJournalState,
  createJournalEventHandlers,
  createJournalLocalSource,
  createJournalEntryPayload,
  loadJournalEntriesFlow,
  loadMoreJournalEntriesFlow,
  createJournalEntryFlow,
  refreshJournalFlow,
} from './features/journal/index.js';
import {
  createClientCreatedJournalEvent,
  createClientSelectedJournalEvent,
  createClientUpdatedJournalEvent,
  createIntegrationStatusJournalEvent,
  createOptimizationActionStatusJournalEvent,
  createSyncStatusJournalEvent,
} from './features/journal/journal-logging.js';
import {
  activeAiBudget as selectActiveAiBudget,
  activeAiModel as selectActiveAiModel,
  createAiAssistantPageContext,
  createAiChatRequestPayload,
  createAiChatStateSnapshot,
  createAiModelStateSnapshot,
  createAiPromptDebugParams,
  createAiAuditJobFlow,
  advanceAiAuditJobFlow,
  generateAiInsightFlow,
  loadAiPromptDebugFlow,
  loadAiStatusFlow,
  requestAiRecommendationsFlow,
  saveAiMemoryNoteFlow,
  sendAiChatMessageFlow,
} from './controllers/ai-controller.js';
import {
  handleAiChangeEvent,
  handleAiClickEvent,
  handleAiInputEvent,
  handleAiSubmitEvent,
} from './controllers/ai-event-bindings.js';
import { renderBusinessContextPanel as renderBusinessContextPanelContent } from './pages/business-context.js';
import * as aiService from './services/ai-service.js';
import * as businessContextService from './services/business-context-service.js';
import * as businessContextStore from './stores/business-context-store.js';
import * as clientsService from './services/clients-service.js';
import {
  createClientFlow,
  createClientSettingsPayload,
  createClientSettingsDraftFromForm,
  deleteClientFlow,
  loadClientsFromApiFlow,
  saveClientSettingsFlow,
} from './controllers/clients-controller.js';
import * as integrationsService from './services/integrations-service.js';
import {
  bindClientYandexAccountFlow,
  loadClientYandexIntegrationFlow,
  loadIntegrationStatusFlow,
  startYandexOAuthFlow,
  unbindClientYandexAccountFlow,
} from './controllers/integrations-controller.js';
import * as optimizationService from './services/optimization-service.js';
import {
  createOptimizationDraftsFromPlanFlow,
  loadOptimizationActionsFlow,
  loadOptimizationExecutionPreviewFlow,
  loadOptimizationPlanFlow,
  updateOptimizationActionStatusFlow,
} from './controllers/optimization-controller.js';
import * as optimizationStore from './stores/optimization-store.js';
import * as performanceService from './services/performance-service.js';
import * as syncService from './services/sync-service.js';
import * as aiStore from './stores/ai-store.js';
import { createAiFeatureState, resetAiClientScopedState } from './stores/ai-feature-state.js';
import * as campaignStore from './stores/campaign-store.js';
import * as clientStore from './stores/client-store.js';
import {
  agencyMetrics,
  auditIssues,
  autopilotRules,
  campaigns,
  clients as initialClients,
  recommendations,
  reportBullets,
} from './data.js';

const app = document.querySelector('#app');
const page = document.body.dataset.page ?? 'landing';
const currentEmail = getCurrentEmail();

if (page === 'app' && !getSessionToken()) {
  window.location.href = 'login.html';
  throw new Error('Authentication required');
}

const navItems = [
  { id: 'dashboard', label: 'Обзор', icon: '📊' },
  { id: 'diagnostics', label: 'Диагностика', icon: '🧪' },
  { id: 'clients', label: 'Клиенты и интеграции', icon: '👥' },
  { id: 'business-context', label: 'Контекст бизнеса', icon: '🧭' },
  { id: 'ai', label: 'AI-аналитик', icon: '🧠' },
  { id: 'optimization', label: 'Оптимизация', icon: '🎯' },
  { id: 'wordstat', label: 'Wordstat', icon: '📈' },
  { id: 'journal', label: 'Журнал', icon: '🕘' },
  { id: 'settings', label: 'Настройки', icon: '⚙️' },
];
function normalizeAppView(view) {
  return page === 'app' ? normalizeAppRouteId(view) : view;
}

const appQueryParams = new URLSearchParams(window.location.search);
const oauthReturnStatus = appQueryParams.get('yandex');
let activeView = page === 'login' ? 'login' : page === 'app' ? 'dashboard' : 'landing';
if (page === 'app' && appQueryParams.get('view')) {
  activeView = normalizeAppView(appQueryParams.get('view'));
}
const storedApiBase = window.localStorage.getItem('directpilot_api_base');
let apiBaseDraft = storedApiBase || API_BASE;
let authEmail = currentEmail || window.localStorage.getItem('directpilot_auth_email') || '';
let authCode = '';
let authStatus = '';
let authStep = 'email';
let authLoading = false;
let selectedClientId = '';
let accountClients = [...initialClients];
let backendClientsLoaded = false;
let backendClientsLoading = false;
let backendClientsAvailable = false;
let backendClientsStatus = 'Клиенты хранятся локально. Backend пока не проверен.';
let clientFormStatus = '';
let clientDraftName = '';
let clientDraftDirectLogin = '';
let clientDraftMetricaCounter = '';
let clientSettingsDraft = null;
let clientSettingsSaving = false;
let clientSettingsStatus = '';
let integrationStatus = { connected: undefined, message: '', accounts: [] };
let clientYandexIntegration = null;
let clientYandexLoading = false;
let clientYandexStatus = '';
let syncLoading = false;
let syncStatusMessage = '';
let syncJobs = [];
let syncJobsLoading = false;
let syncJobsLoadedFor = '';
let syncJobsInFlightFor = '';
let syncJobsLastLoadedAt = 0;
const SYNC_JOBS_REFRESH_MS = 60 * 1000;
let perfSummary = null;
let perfLoading = false;
let perfStatus = '';
let performanceCampaignSearch = '';
let performanceRangeState = {
  preset: 'yesterday',
  dateFrom: '',
  dateTo: '',
  loading: false,
  status: '',
  summary: null,
};
let optimizationPlan = null;
let optimizationPlanLoading = false;
let optimizationStatus = '';
let optimizationFilter = 'all';
let optimizationActions = [];
let optimizationActionsLoading = false;
let optimizationActionsStatus = '';
let optimizationActionsLoadedFor = '';
let optimizationActionFilter = 'all';
let optimizationExecutionPreviews = {};
let businessContext = null;
let businessContextLoading = false;
let businessContextStatus = '';
let businessContextSaving = false;
let businessContextDraft = null;
let businessContextLoadedFor = '';
const CUSTOM_MODEL_VALUE = aiStore.CUSTOM_MODEL_VALUE;
const aiFeatureState = createAiFeatureState();
const journalSource = createJournalLocalSource();
let journalState = createInitialJournalState();
let journalLoadedFor = '';
let aiChatShouldScrollToBottom = false;
let aiAuditPollTimer = 0;
let aiAuditRefreshInFlight = false;

function storageKey(key) {
  return scopedStorageKey(key);
}

function aiAuditStorageKey(clientId = selectedClientId) {
  return storageKey(`directpilot_ai_audit_job_${clientId || 'none'}`);
}

function stopAiAuditPolling() {
  if (aiAuditPollTimer) window.clearTimeout(aiAuditPollTimer);
  aiAuditPollTimer = 0;
}

function normalizeAiModelState() {
  aiFeatureState.model.selectedModel = aiStore.normalizeProductionAiModel(aiFeatureState.model.selectedModel);
  if (!['economy', 'balanced', 'advanced', 'deep'].includes(aiFeatureState.model.selectedPreset)) {
    aiFeatureState.model.selectedPreset = 'balanced';
  }
  if (aiFeatureState.model.selectedPreset === 'deep') {
    aiFeatureState.model.selectedPreset = 'advanced';
  }
  if (!['compact', 'deep'].includes(aiFeatureState.model.maxTokensMode)) {
    aiFeatureState.model.maxTokensMode = 'compact';
  }
  if (!['summary', 'raw'].includes(aiFeatureState.model.toolResultsMode)) {
    aiFeatureState.model.toolResultsMode = 'summary';
  }
  aiFeatureState.model.chatHistoryLimit = [1, 3, 6].includes(Number(aiFeatureState.model.chatHistoryLimit))
    ? Number(aiFeatureState.model.chatHistoryLimit)
    : 3;
  aiFeatureState.model.searchQueryLimit = String(Number(aiFeatureState.model.searchQueryLimit) || 20);
  aiFeatureState.model.compactContext = aiFeatureState.model.compactContext !== false;
  aiFeatureState.model.customModel = '';
}

function loadAiModelSettings() {
  try {
    const raw = window.localStorage.getItem(storageKey('directpilot_ai_model_settings'));
    if (!raw) {
      normalizeAiModelState();
      return;
    }
    const saved = JSON.parse(raw);
    if (saved && typeof saved === 'object') {
      aiFeatureState.model.selectedModel = saved.selectedModel || saved.model || aiFeatureState.model.selectedModel;
      aiFeatureState.model.selectedPreset = saved.selectedPreset || saved.preset || aiFeatureState.model.selectedPreset;
      aiFeatureState.model.maxTokensMode = saved.maxTokensMode || aiFeatureState.model.maxTokensMode;
      aiFeatureState.model.compactContext = saved.compactContext !== undefined ? Boolean(saved.compactContext) : aiFeatureState.model.compactContext;
      aiFeatureState.model.toolResultsMode = saved.toolResultsMode || aiFeatureState.model.toolResultsMode;
      aiFeatureState.model.chatHistoryLimit = Number(saved.chatHistoryLimit) || aiFeatureState.model.chatHistoryLimit;
      aiFeatureState.model.searchQueryLimit = saved.searchQueryLimit || aiFeatureState.model.searchQueryLimit;
    }
  } catch (error) {
    console.warn('Could not load AI model settings', error);
  }
  normalizeAiModelState();
}

function saveAiModelSettings() {
  normalizeAiModelState();
  window.localStorage.setItem(storageKey('directpilot_ai_model_settings'), JSON.stringify({
    selectedModel: aiFeatureState.model.selectedModel,
    selectedPreset: aiFeatureState.model.selectedPreset,
    maxTokensMode: aiFeatureState.model.maxTokensMode,
    compactContext: aiFeatureState.model.compactContext,
    toolResultsMode: aiFeatureState.model.toolResultsMode,
    chatHistoryLimit: aiFeatureState.model.chatHistoryLimit,
    searchQueryLimit: aiFeatureState.model.searchQueryLimit,
  }));
}

if (page === 'app') {
  loadAiModelSettings();
}

const clientsStore = clientStore.createClientStore(storageKey);
const campaignsStore = campaignStore.createCampaignStore();

function loadSelectedClientId() {
  return clientStore.loadSelectedClientId(storageKey, accountClients[0]?.id || '');
}

function saveSelectedClientId(clientId) {
  clientStore.saveSelectedClientId(storageKey, clientId);
}

async function loadClientsFromApi(force = false) {
  const selectedClientBeforeLoad = selectedClientId;
  await loadClientsFromApiFlow({
    page,
    force,
    loading: backendClientsLoading,
    loaded: backendClientsLoaded,
    businessContextLoading,
    clientsService,
    clientsStore,
    loadSelectedClientId,
    onStart: () => {
      backendClientsLoading = true;
    },
    onSuccess: ({ clients, selectedClientId: nextSelectedClientId, message, shouldResetBusinessContext }) => {
      accountClients = clients;
      backendClientsLoaded = true;
      backendClientsAvailable = true;
      backendClientsStatus = message;
      selectedClientId = nextSelectedClientId;
      if (selectedClientId) saveSelectedClientId(selectedClientId);
      clientsStore.saveStoredClients(accountClients);
      if (selectedClientId !== selectedClientBeforeLoad) {
        resetClientScopedUiState({ nextActiveView: activeView });
      }
      if (shouldResetBusinessContext) businessContext = null;
    },
    onFallback: ({ clients, selectedClientId: fallbackSelectedClientId, message }) => {
      if (!backendClientsLoaded && clients.length) {
        accountClients = clients;
        selectedClientId = fallbackSelectedClientId || '';
        if (selectedClientId !== selectedClientBeforeLoad) {
          resetClientScopedUiState({ nextActiveView: activeView });
        }
      }
      backendClientsAvailable = false;
      backendClientsStatus = message;
    },
    onFinally: () => {
      backendClientsLoading = false;
      render();
    },
  });
}


const localClients = clientsStore.loadStoredClients();
if (localClients.length) {
  accountClients = localClients;
}
selectedClientId = loadSelectedClientId();
if (!accountClients.find((client) => client.id === selectedClientId)) {
  selectedClientId = accountClients[0]?.id || '';
}
if (selectedClientId) saveSelectedClientId(selectedClientId);

function currentClient() {
  return clientsStore.getCurrentClient(accountClients, selectedClientId);
}

function currentClientName() {
  return currentClient().name || 'Клиент не выбран';
}

function resetClientScopedUiState({ nextActiveView = activeView } = {}) {
  stopAiAuditPolling();
  applyClientScopeResetPatch((patch) => {
    businessContext = patch.businessContext;
    businessContextDraft = patch.businessContextDraft;
    businessContextLoadedFor = '';
    clientYandexIntegration = patch.clientYandexIntegration;
    clientYandexStatus = '';
    clientYandexLoading = false;
    syncJobs = patch.syncJobs;
    syncJobsLoading = false;
    syncJobsLoadedFor = '';
    syncJobsInFlightFor = '';
    syncJobsLastLoadedAt = 0;
    syncStatusMessage = '';
    perfSummary = patch.perfSummary;
    perfLoading = false;
    perfStatus = '';
    performanceRangeState = {
      ...performanceRangeState,
      loading: false,
      status: '',
      summary: null,
    };
    performanceCampaignSearch = '';
    optimizationPlan = patch.optimizationPlan;
    optimizationPlanLoading = false;
    optimizationStatus = '';
    optimizationActions = patch.optimizationActions;
    optimizationActionsLoading = false;
    optimizationActionsStatus = '';
    optimizationActionsLoadedFor = patch.optimizationActionsLoadedFor;
    optimizationExecutionPreviews = patch.optimizationExecutionPreviews;
    journalState = createInitialJournalState();
    journalState.filters = createDefaultJournalFilters({ clientId: selectedClientId || null });
    journalLoadedFor = patch.journalLoadedFor;
    activeView = nextActiveView;
  }, createClientScopeResetPatch({ activeView: nextActiveView }));
  resetAiClientScopedState(aiFeatureState);
}

function currentJournalActor() {
  return {
    kind: 'user',
    id: currentEmail,
    label: currentEmail || 'User',
  };
}

async function logJournalEvent(input = {}) {
  if (!input || typeof input !== 'object') return null;
  return createJournalEntry({
    scope: selectedClientId ? 'client' : input.scope || 'system',
    clientId: selectedClientId || input.clientId || null,
    actor: currentJournalActor(),
    ...input,
  });
}

function formatNumberSafe(value) {
  const numeric = typeof value === 'number' ? value : Number(String(value ?? '').replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(numeric) ? new Intl.NumberFormat('ru-RU').format(numeric) : '0';
}

function formatMoney(value) {
  return `${formatNumberSafe(value)} ₽`;
}

function formatPercent(value) {
  const numeric = typeof value === 'number' ? value : Number(String(value ?? '').replace(/\s/g, '').replace(',', '.'));
  if (!Number.isFinite(numeric)) return '0%';
  return `${numeric.toFixed(1).replace('.', ',')}%`;
}

function performancePeriodPresetLabel(preset) {
  return {
    today: 'Сегодня',
    yesterday: 'Вчера',
    '3d': '3 дня',
    '7d': '7 дней',
    '14d': '14 дней',
    '30d': '30 дней',
    this_month: 'Этот месяц',
    custom: 'Свой период',
  }[preset] || 'Выбранный период';
}

function performancePeriodLabel(summary = performanceRangeState.summary) {
  const period = summary?.period;
  if (!period) return performancePeriodPresetLabel(performanceRangeState.preset);
  const label = performancePeriodPresetLabel(period.preset || performanceRangeState.preset);
  return `${label}: ${period.dateFrom || period.from || '—'} — ${period.dateTo || period.to || '—'}`;
}

function mapRangeCampaignToSummaryCampaign(campaign = {}) {
  return {
    campaign_id: campaign.campaignId || campaign.campaign_id || '',
    campaign_name: campaign.campaignName || campaign.campaign_name || campaign.name || '',
    impressions: campaign.impressions || 0,
    clicks: campaign.clicks || 0,
    ctr: campaign.ctr || 0,
    cost: campaign.cost || 0,
    goal_conversions: campaign.goalConversions ?? campaign.goal_conversions ?? 0,
    cpa_used: campaign.goalCpa ?? campaign.goal_cpa ?? campaign.cpa_used ?? 0,
    severity: campaign.severity || '',
    issue_flags: campaign.issueFlags || campaign.issue_flags || [],
  };
}

function performanceTableSummary() {
  if (performanceRangeState.summary?.campaigns?.length) {
    const summary = performanceRangeState.summary;
    return {
      period: {
        from: summary.period?.dateFrom,
        to: summary.period?.dateTo,
      },
      selectedGoalIds: summary.selectedGoalIds || [],
      totals: {
        cost: summary.totals?.cost || 0,
        impressions: summary.totals?.impressions || 0,
        clicks: summary.totals?.clicks || 0,
        conversions: summary.totals?.goalConversions || 0,
      },
      goalConversionsTotal: summary.totals?.goalConversions || 0,
      campaigns: summary.campaigns.map(mapRangeCampaignToSummaryCampaign),
      searchQueryInsights: perfSummary?.searchQueryInsights || null,
    };
  }
  return perfSummary;
}

function hasConnectedDirectLogin(value) {
  return Boolean(value && value !== 'Не подключен');
}


function canRunSync() {
  const client = currentClient();
  return Boolean(client.id && client.directLogin && client.directLogin !== 'Не подключен');
}

function syncJobStatusLabel(status) {
  return {
    completed: 'Завершено',
    failed: 'Ошибка',
    running: 'В процессе',
    pending: 'Ожидает',
  }[status] || status || 'Неизвестно';
}

function normalizeDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('ru-RU');
  } catch (error) {
    return value;
  }
}

const spend = agencyMetrics.reduce((sum, item) => sum + item.spend, 0);
const leads = agencyMetrics.reduce((sum, item) => sum + item.leads, 0);
const revenue = agencyMetrics.reduce((sum, item) => sum + item.revenue, 0);
const avgCpl = Math.round(spend / leads);
const avgRoi = Math.round((revenue / spend) * 100);

function renderLanding() {
  return `
    <header class="hero">
      <nav class="topNav">
        <div class="brand"><span class="logo">D</span><span>DirectPilot AI</span></div>
        <div class="navLinks"><a href="#features">Возможности</a><a href="#workflow">Как работает</a><a href="#pricing">Тарифы</a><a class="loginLink" href="login.html">Войти</a></div>
      </nav>
      <div class="heroGrid">
        <div>
          <span class="eyebrow">AI-сервис для агентств и специалистов по Яндекс.Директу</span>
          <h1>Автоматизируйте аудит, отчёты и оптимизацию рекламных кампаний</h1>
          <p>DirectPilot AI подключается к Метрике, Директу и вашим клиентским данным, находит слабые места, формирует рекомендации и готовит отчёты в стиле вашего агентства.</p>
          <div class="heroActions"><a class="primaryButton" href="login.html">Начать бесплатно</a><a class="secondaryButton" href="#workflow">Посмотреть процесс</a></div>
        </div>
        <div class="heroCard">
          <div class="scoreHeader"><span>AI-аудит кампании</span><strong>92%</strong></div>
          <div class="progress"><span style="width:92%"></span></div>
          <ul>
            <li>3 кампании с перерасходом бюджета</li>
            <li>18 минус-слов к добавлению</li>
            <li>2 сегмента готовы к масштабированию</li>
          </ul>
        </div>
      </div>
    </header>
    <section id="features" class="section"><h2>Что берёт на себя AI</h2><div class="featureGrid">
      <article><span>01</span><h3>Аудит кампаний</h3><p>Проверка структуры, ставок, поисковых запросов, минус-слов и посадочных страниц.</p></article>
      <article><span>02</span><h3>Рекомендации</h3><p>AI объясняет, что исправить, какой эффект ждать и какие действия согласовать с клиентом.</p></article>
      <article><span>03</span><h3>Отчётность</h3><p>Еженедельные и месячные отчёты с выводами, KPI и планом работ без ручной сборки.</p></article>
    </div></section>
    <section id="workflow" class="section split"><div><span class="eyebrow">Процесс</span><h2>Подключите данные один раз — получайте план действий каждый день</h2><p>Сервис собирает статистику, анализирует отклонения и предлагает оптимизации. Специалист остаётся главным: он проверяет, согласует и применяет изменения.</p></div><div class="steps"><div>Подключение Метрики и Директа</div><div>Импорт KPI и целей клиента</div><div>AI-аудит и рекомендации</div><div>Согласование и отчёт</div></div></section>
    <section id="pricing" class="section cta"><h2>Соберите пилотный кабинет для первых клиентов</h2><p>Начните с демо-версии, подключите 1–3 проекта и оцените экономию времени на регулярной аналитике.</p><a class="primaryButton" href="login.html">Войти в кабинет</a></section>
  `;
}

function renderLogin() {
  return `
    <section class="loginPage">
      <div class="loginCard">
        <div class="brand"><span class="logo">D</span><span>DirectPilot AI</span></div>
        <h1>${authStep === 'code' ? 'Введите код из письма' : 'Вход по email'}</h1>
        <p>${authStep === 'code' ? 'Мы отправили одноразовый код на почту. После подтверждения вы попадёте в кабинет.' : 'Введите рабочий email, и мы отправим код для входа без пароля.'}</p>
        <form class="loginForm" data-auth-form>
          ${authStep === 'email' ? `
            <label>Email</label>
            <input name="email" type="email" value="${escapeHtml(authEmail)}" placeholder="you@agency.ru" required />
          ` : `
            <label>Код подтверждения</label>
            <input name="code" inputmode="numeric" value="${escapeHtml(authCode)}" placeholder="123456" required />
          `}
          <button class="primaryButton" type="submit" ${authLoading ? 'disabled' : ''}>${authLoading ? 'Проверяем...' : authStep === 'code' ? 'Подтвердить' : 'Получить код'}</button>
        </form>
        ${authStep === 'code' ? `<button class="linkButton" data-auth-back>Изменить email</button>` : ''}
        ${authStatus ? `<div class="authStatus">${escapeHtml(authStatus)}</div>` : ''}
      </div>
    </section>
  `;
}

function renderShell(content) {
  const client = currentClient();
  const showClientSelector = page === 'app';
  const progress = showClientSelector ? readinessProgress() : { ready: 0, total: 0 };
  return `
    <div class="appShell">
      <aside class="sidebar">
        <div class="brand"><span class="logo">D</span><span>DirectPilot AI</span></div>
        ${showClientSelector ? renderSidebarClientSwitcher(client, progress) : `
          <div class="clientMini">
            <span>Аккаунт</span>
            <strong>${escapeHtml(currentEmail || 'Гость')}</strong>
          </div>
        `}
        <nav>${navItems.map((item) => `<button class="${activeView === item.id ? 'active' : ''}" data-view="${item.id}"><span>${item.icon}</span>${item.label}</button>`).join('')}</nav>
        <button class="logoutButton" data-logout>Выйти</button>
      </aside>
      <main class="dashboard">
        <header class="dashboardHeader">
          <div>
            <span class="eyebrow">Кабинет</span>
            <h1>${escapeHtml(activeView === 'dashboard' ? 'Обзор проекта' : navItems.find((item) => item.id === activeView)?.label || 'DirectPilot')}</h1>
          </div>
          <div class="headerActions"></div>
        </header>
        ${content}
      </main>
    </div>
  `;
}

function renderSidebarClientSwitcher(client = currentClient(), progress = readinessProgress()) {
  if (!accountClients.length) {
    return `
      <div class="clientMini sidebarClientSwitcher">
        <span>Активный клиент</span>
        <strong>Не выбран</strong>
        <small>Готовность 0/6</small>
        <button class="secondaryButton" type="button" data-view="clients">Добавить клиента</button>
      </div>
    `;
  }
  return `
    <div class="clientMini sidebarClientSwitcher">
      <span>Активный клиент</span>
      <strong>${escapeHtml(client.name || 'Клиент')}</strong>
      <small>Готовность ${formatNumberSafe(progress.ready)}/${formatNumberSafe(progress.total)}</small>
      <div class="sidebarClientActions">
        <button class="secondaryButton" type="button" data-client-menu-toggle>Сменить</button>
        <button class="secondaryButton" type="button" data-view="clients">Добавить</button>
      </div>
      <div class="clientMenu sidebarClientMenu" data-client-menu hidden>
        ${accountClients.map((item) => `<button type="button" data-client-id="${escapeHtml(item.id)}" class="${item.id === selectedClientId ? 'active' : ''}">${escapeHtml(item.name)}<small>${escapeHtml(item.directLogin || 'Direct не подключен')}</small></button>`).join('')}
      </div>
    </div>
  `;
}

function renderProfilePanel() {
  return `
    <section class="settingsPanel profilePanel" data-profile-panel hidden>
      <strong>Профиль</strong>
      <small>Email: ${escapeHtml(currentEmail || 'не указан')}</small>
      <small>Backend: ${escapeHtml(backendClientsAvailable ? 'подключён' : 'не проверен')}</small>
      <small>API: ${escapeHtml(API_BASE)}</small>
      <button class="secondaryButton" type="button" data-open-settings>API URL</button>
    </section>
  `;
}

function renderClientContextStrip(client = currentClient()) {
  const hasClient = Boolean(client?.id);
  const directReady = Boolean(client?.directLogin && client.directLogin !== 'Не подключен');
  const metricaReady = Boolean(client?.metricaCounter && client.metricaCounter !== 'Не подключен');
  const goals = client?.conversionGoalIds || client?.mainGoalId || '';
  const goalsReady = Boolean(goals);
  const yandexReady = Boolean(client?.yandexAccountId || getBoundYandexAccountId());
  const latestJob = { status: client?.syncStatus || 'never_synced' };
  const syncReady = ['success', 'completed'].includes(latestJob.status) || hasPerformanceData();
  const syncStatus = syncLoading ? 'loading' : ['error', 'failed'].includes(latestJob.status) ? 'error' : syncReady ? 'ready' : 'pending';
  const item = (label, value, status) => `
    <article class="clientContextItem ${badgeClassForStatus(status)}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(compactStatusLabel(status))}</em>
    </article>
  `;

  return `
    <section class="clientContextStrip" aria-label="Рабочий контекст клиента">
      ${item('Клиент', hasClient ? client.name || 'Без названия' : 'Не выбран', hasClient ? 'ready' : 'action_needed')}
      ${item('Direct', directReady ? client.directLogin : 'укажите логин', directReady ? 'ready' : 'action_needed')}
      ${item('Метрика', metricaReady ? client.metricaCounter : 'укажите счётчик', metricaReady ? 'ready' : 'action_needed')}
      ${item('Цели', goalsReady ? goals : 'укажите цели', goalsReady ? 'ready' : 'action_needed')}
      ${item('Яндекс', yandexReady ? 'аккаунт привязан' : 'не привязан', yandexReady ? 'ready' : 'action_needed')}
      ${item('Sync', latestJob ? syncJobStatusLabel(latestJob.status) : 'нет запусков', syncStatus)}
    </section>
  `;
}

function getBoundYandexAccount(integration = clientYandexIntegration) {
  return integration?.bound_account
    || integration?.selected_account
    || integration?.boundAccount
    || integration?.selectedAccount
    || null;
}

function getBoundYandexAccountId(integration = clientYandexIntegration) {
  return getBoundYandexAccount(integration)?.id || integration?.yandex_account_id || integration?.yandexAccountId || '';
}

function getBoundYandexAccountLogin(integration = clientYandexIntegration) {
  const account = getBoundYandexAccount(integration);
  return account?.login || account?.name || account?.display_name || account?.displayName || '';
}

function renderSettingsPanel() {
  return `
    <section class="settingsPanel" data-settings-panel hidden>
      <form data-api-base-form>
        <label>Backend API URL</label>
        <div class="settingsRow">
          <input name="apiBase" value="${escapeHtml(apiBaseDraft)}" placeholder="http://127.0.0.1:8000" />
          <button class="secondaryButton" type="submit">Сохранить</button>
        </div>
        <small>Для локальной разработки можно указать адрес FastAPI. Текущее значение: ${escapeHtml(API_BASE)}</small>
      </form>
    </section>
  `;
}

function renderClientSelector() {
  if (!accountClients.length) {
    return `<button class="clientSelector" data-view="clients"><span>Клиент</span><strong>Создать</strong></button>`;
  }
  return `
    <div class="clientSelectorWrap">
      <button class="clientSelector" data-client-menu-toggle><span>Клиент</span><strong>${escapeHtml(currentClientName())}</strong></button>
      <div class="clientMenu" data-client-menu hidden>
        ${accountClients.map((client) => `<button type="button" data-client-id="${escapeHtml(client.id)}" class="${client.id === selectedClientId ? 'active' : ''}">${escapeHtml(client.name)}<small>${escapeHtml(client.directLogin || 'Direct не подключен')}</small></button>`).join('')}
      </div>
    </div>
  `;
}

function renderActionButton(label, attrs = '', variant = 'secondary') {
  return `<button class="${variant === 'primary' ? 'approveButton' : 'secondaryButton'}" type="button" ${attrs}>${escapeHtml(label)}</button>`;
}

function badgeClassForStatus(status) {
  return status === 'ready' || status === 'approved' || status === 'reviewed' ? 'ready' : 'pending';
}

function compactStatusLabel(status) {
  return {
    ready: 'Готово',
    action_needed: 'Нужно действие',
    blocked: 'Блокер',
    pending: 'Нет данных',
    loading: 'Загрузка',
    error: 'Ошибка',
    draft: 'Черновик',
    reviewed: 'Просмотрено',
    approved: 'Одобрено',
    rejected: 'Отклонено',
    needs_changes: 'Нужны правки',
  }[status] || status || 'Нет данных';
}

function renderReadinessPanel(readiness, nextAction) {
  return `
    <section class="panel readinessPanel">
      <div class="panelHeader">
        <div>
          <h3>Готовность проекта</h3>
          <p>Что уже подключено и что мешает AI делать точные рекомендации.</p>
        </div>
      </div>
      <div class="readinessGrid">
        ${readiness.map((item) => `
          <article class="readinessCard ${badgeClassForStatus(item.status)}">
            <div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.description)}</span></div>
            <span class="aiStatusBadge ${badgeClassForStatus(item.status)}">${escapeHtml(compactStatusLabel(item.status))}</span>
          </article>
        `).join('')}
      </div>
      ${nextAction ? `<div class="authStatus integrationStatus"><strong>Фокус:</strong> ${escapeHtml(nextAction.nextAction)}</div>` : ''}
    </section>
  `;
}

function getReadinessState() {
  const client = currentClient();
  const hasClient = Boolean(client.id);
  const hasDirectLogin = Boolean(client.directLogin && client.directLogin !== 'Не подключен');
  const hasMetrica = Boolean(client.metricaCounter && client.metricaCounter !== 'Не подключен');
  const hasYandexBinding = Boolean(client.yandexAccountId || getBoundYandexAccountId());
  const hasSync = ['success', 'completed'].includes(client.syncStatus) || hasPerformanceData();
  const hasGoals = Boolean(client.mainGoalId || client.conversionGoalIds);
  const hasContext = hasBusinessContextData(businessContext);
  const hasOptimizationDrafts = optimizationActions.length > 0;

  return [
    {
      id: 'client',
      label: 'Клиент',
      status: hasClient ? 'ready' : 'action_needed',
      description: hasClient ? `Выбран «${client.name}».` : 'Создайте карточку клиента.',
    },
    {
      id: 'yandex',
      label: 'Привязка Яндекса',
      status: hasYandexBinding ? 'ready' : hasDirectLogin ? 'action_needed' : 'blocked',
      description: hasYandexBinding ? 'Аккаунт Яндекса привязан к клиенту.' : hasDirectLogin ? 'Нужно выбрать аккаунт из OAuth-доступов.' : 'Сначала укажите логин Директа.',
    },
    {
      id: 'metrica',
      label: 'Метрика и цели',
      status: hasMetrica && hasGoals ? 'ready' : hasMetrica ? 'action_needed' : 'blocked',
      description: hasMetrica && hasGoals ? 'Счётчик и цели указаны.' : hasMetrica ? 'Добавьте основную цель и цели конверсий.' : 'Укажите ID счётчика Метрики.',
    },
    {
      id: 'context',
      label: 'Контекст бизнеса',
      status: hasContext ? 'ready' : 'action_needed',
      description: hasContext ? 'AI знает продукт, аудиторию и ограничения.' : 'Заполните нишу, продукт, географию и офферы.',
    },
    {
      id: 'sync',
      label: 'Синхронизация',
      status: hasSync ? 'ready' : canRunSync() ? 'action_needed' : 'blocked',
      description: hasSync ? 'Есть свежие данные для анализа.' : canRunSync() ? 'Запустите первую синхронизацию.' : 'Нужен клиент и логин Директа.',
    },
    {
      id: 'optimization',
      label: 'Черновики действий',
      status: hasOptimizationDrafts ? 'ready' : hasPerformanceData() ? 'action_needed' : 'pending',
      description: hasOptimizationDrafts ? 'Есть черновики для согласования.' : hasPerformanceData() ? 'Сформируйте план оптимизации.' : 'Появятся после загрузки статистики.',
    },
  ];
}

function getNextBestAction() {
  const readiness = getReadinessState();
  const blocking = readiness.find((item) => item.status === 'blocked' || item.status === 'action_needed');
  if (!blocking) {
    return {
      label: 'Проект готов',
      status: 'ready',
      description: 'Все базовые данные подключены. Можно переходить к оптимизации и AI-рекомендациям.',
      nextAction: 'Откройте AI-аналитика или план оптимизации.',
      targetView: 'ai',
    };
  }
  const actions = {
    client: ['Создайте клиента', 'clients'],
    yandex: ['Привяжите аккаунт Яндекса', 'clients'],
    metrica: ['Заполните цели и счётчик', 'clients'],
    context: ['Заполните контекст бизнеса', 'business-context'],
    sync: ['Запустите синхронизацию', 'dashboard'],
    optimization: ['Сформируйте черновики оптимизации', 'optimization'],
  };
  const [nextAction, targetView] = actions[blocking.id] || ['Проверьте настройки', 'dashboard'];
  return { ...blocking, nextAction, targetView };
}

function readinessProgress() {
  const readiness = getReadinessState();
  const ready = readiness.filter((item) => item.status === 'ready').length;
  return { ready, total: readiness.length };
}

function hasPerformanceData() {
  return Boolean(perfSummary && (perfSummary.campaigns?.length || perfSummary.searchQueryInsights));
}

function normalizeBusinessContext(payload) {
  return businessContextStore.normalizeBusinessContext(payload);
}

function businessContextPayload(context) {
  return businessContextStore.createBusinessContextPayload(context);
}

function defaultBusinessContext() {
  return businessContextStore.createDefaultBusinessContext(currentClient());
}

function hasBusinessContextData(context) {
  return businessContextStore.hasBusinessContextData(context);
}

function businessContextCopyText(context = businessContext || businessContextDraft || defaultBusinessContext()) {
  return businessContextStore.createBusinessContextCopyText(context);
}

function setBusinessContextDraftFromForm(form) {
  businessContextDraft = businessContextStore.createBusinessContextDraftFromForm(form);
  return businessContextDraft;
}

function businessContextForAi() {
  return businessContextStore.createBusinessContextForAi(businessContext, businessContextDraft);
}

function contextCompletenessScore(context = businessContext || businessContextDraft) {
  return businessContextStore.calculateBusinessContextCompletenessScore(context);
}

function campaignOptions() {
  return campaignsStore.getCampaignOptions(perfSummary);
}

function currentAiModelState() {
  return createAiModelStateSnapshot({
    aiStatus: aiFeatureState.model.status,
    selectedAiModel: aiFeatureState.model.selectedModel,
    customAiModel: aiFeatureState.model.customModel,
    selectedAiPreset: aiFeatureState.model.selectedPreset,
    aiMaxTokensMode: aiFeatureState.model.maxTokensMode,
    aiCompactContext: aiFeatureState.model.compactContext,
    aiToolResultsMode: aiFeatureState.model.toolResultsMode,
    aiChatHistoryLimit: aiFeatureState.model.chatHistoryLimit,
    aiSearchQueryLimit: aiFeatureState.model.searchQueryLimit,
  });
}

function currentAiChatState() {
  return createAiChatStateSnapshot({
    aiChatMessages: aiFeatureState.chat.messages,
    aiChatInput: aiFeatureState.chat.input,
    aiChatLoading: aiFeatureState.chat.loading,
    aiChatError: aiFeatureState.chat.error,
    aiChatErrorDetails: aiFeatureState.chat.errorDetails,
    aiChatToolTraces: aiFeatureState.chat.toolTraces,
    aiChatSelectedCampaignName: aiFeatureState.chat.selectedCampaignName,
  });
}

function activeAiModel() {
  return selectActiveAiModel(currentAiModelState());
}

function activeAiBudget() {
  return selectActiveAiBudget(currentAiModelState());
}

function aiChatRequestPayload(message) {
  return createAiChatRequestPayload({
    clientId: selectedClientId,
    message,
    modelState: currentAiModelState(),
    chatState: currentAiChatState(),
    businessContext: businessContextForAi(),
  });
}

function aiPromptDebugParams() {
  return createAiPromptDebugParams(currentAiModelState(), aiFeatureState.chat.selectedCampaignName, currentAiChatState());
}

function requestAiChatScrollToBottom() {
  aiChatShouldScrollToBottom = true;
}

function scrollAiChatToBottom() {
  const chatMessages = app.querySelector('[data-ai-chat-messages]');
  if (chatMessages) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  aiChatShouldScrollToBottom = false;
}

async function loadAiPromptDebug() {
  await loadAiPromptDebugFlow({
    selectedClientId,
    params: aiPromptDebugParams(),
    aiService,
    onMissingClient: (message) => {
      aiFeatureState.generation.promptDebugError = message;
      render();
    },
    onStart: () => {
      aiFeatureState.generation.promptDebugLoading = true;
      aiFeatureState.generation.promptDebugError = '';
      render();
    },
    onSuccess: (promptDebug) => {
      aiFeatureState.generation.promptDebug = promptDebug;
    },
    onError: (message) => {
      aiFeatureState.generation.promptDebugError = message;
    },
    onFinally: () => {
      aiFeatureState.generation.promptDebugLoading = false;
      render();
    },
  });
}


async function requestAiRecommendations() {
  const budget = activeAiBudget();

  await requestAiRecommendationsFlow({
    selectedClientId,
    params: {
      model: activeAiModel(),
      ai_preset: aiFeatureState.model.selectedPreset === 'deep' ? 'advanced' : aiFeatureState.model.selectedPreset,
      max_tokens: budget.maxTokens,
      target_context_tokens: budget.targetContextTokens,
      include_business_context: true,
      business_context: businessContextForAi(),
      compact_context: aiFeatureState.model.compactContext,
      include_raw_tool_results: aiFeatureState.model.toolResultsMode === 'raw' || budget.includeRawToolResults,
      search_query_limit: Number(aiFeatureState.model.searchQueryLimit) || 20,
    },
    aiService,
    saveMemoryNote: saveAiMemoryNote,
    onMissingClient: (message) => {
      aiFeatureState.generation.recommendationsError = message;
      render();
    },
    onStart: () => {
      aiFeatureState.generation.recommendationsLoading = true;
      aiFeatureState.generation.recommendationsError = '';
      render();
    },
    onSuccess: (payload) => {
      aiFeatureState.generation.clientRecommendations = payload;
    },
    onError: (message) => {
      aiFeatureState.generation.recommendationsError = message;
    },
    onFinally: () => {
      aiFeatureState.generation.recommendationsLoading = false;
      render();
    },
  });
}


async function sendAiChatMessage(message) {
  const text = String(message || aiFeatureState.chat.input || '').trim();
  if (aiStore.requiresStagedAudit(text)) {
    await startAiAudit('full_account', text);
    return;
  }
  await sendAiChatMessageFlow({
    message: text,
    loading: aiFeatureState.chat.loading,
    currentChatState: currentAiChatState,
    createRequestPayload: aiChatRequestPayload,
    addChatMessage: aiStore.addAiChatMessage,
    aiService,
    saveMemoryNote: saveAiMemoryNote,
    onStart: ({ messages }) => {
      aiFeatureState.chat.messages = messages;
      aiFeatureState.chat.input = '';
      aiFeatureState.chat.loading = true;
      aiFeatureState.chat.error = '';
      aiFeatureState.chat.errorDetails = null;
      requestAiChatScrollToBottom();
      render();
    },
    onSuccess: ({ messages, toolTraces }) => {
      aiFeatureState.chat.messages = messages;
      aiFeatureState.chat.toolTraces = toolTraces;
      requestAiChatScrollToBottom();
    },
    onError: ({ message: errorMessage, payload, messages }) => {
      aiFeatureState.chat.error = errorMessage;
      aiFeatureState.chat.errorDetails = payload;
      if (messages) {
        aiFeatureState.chat.messages = messages;
      }
      requestAiChatScrollToBottom();
    },
    onFinally: () => {
      aiFeatureState.chat.loading = false;
      render();
    },
  });
}


function persistAiAuditJob(job) {
  if (!selectedClientId) return;
  if (job?.job_id) window.localStorage.setItem(aiAuditStorageKey(), job.job_id);
  else window.localStorage.removeItem(aiAuditStorageKey());
}

function showCompletedAiAudit(job) {
  if (!job?.answer || aiFeatureState.audit.completedShownJobId === job.job_id) return;
  aiFeatureState.audit.completedShownJobId = job.job_id;
  const content = job.result?.structured
    ? job.answer
    : 'Аудит завершён, но модель вернула неподдерживаемый формат. Технический ответ доступен в блоке аудита.';
  aiFeatureState.chat.messages = aiStore.addAiChatMessage(currentAiChatState(), {
    role: 'assistant',
    content,
    auditJobId: job.job_id,
  }).messages;
  requestAiChatScrollToBottom();
}

function applyAiAuditJob(job) {
  const current = aiFeatureState.audit.job;
  const incomingUpdatedAt = Date.parse(job?.updated_at || '');
  const currentUpdatedAt = Date.parse(current?.updated_at || '');
  if (current?.job_id === job?.job_id
    && Number.isFinite(incomingUpdatedAt)
    && Number.isFinite(currentUpdatedAt)
    && incomingUpdatedAt < currentUpdatedAt) {
    return;
  }
  aiFeatureState.audit.job = job;
  aiFeatureState.audit.error = '';
  persistAiAuditJob(job);
  if (job?.status === 'completed') showCompletedAiAudit(job);
}

function aiAuditStatusCanAdvance(status) {
  return ['queued', 'context_ready'].includes(String(status || ''));
}

function scheduleAiAuditProgress(delayMs = 1800, forceRefresh = false) {
  stopAiAuditPolling();
  const job = aiFeatureState.audit.job;
  if (activeView !== 'ai' || !job?.job_id || aiStore.isTerminalAiAuditStatus(job.status)) return;
  aiAuditPollTimer = window.setTimeout(() => {
    aiAuditPollTimer = 0;
    if (!forceRefresh && !aiFeatureState.audit.loading && aiAuditStatusCanAdvance(aiFeatureState.audit.job?.status)) {
      void advanceActiveAiAudit();
    } else {
      void refreshActiveAiAudit();
    }
  }, Math.max(1500, Number(delayMs) || 1800));
}

async function startAiAudit(scope = 'full_account', requestedMessage = '') {
  if (!selectedClientId || aiFeatureState.audit.loading) return;
  stopAiAuditPolling();
  if (requestedMessage) {
    aiFeatureState.chat.messages = aiStore.addAiChatMessage(currentAiChatState(), {
      role: 'user',
      content: requestedMessage,
    }).messages;
    aiFeatureState.chat.input = '';
  }
  await createAiAuditJobFlow({
    request: {
      client_id: selectedClientId,
      scope,
      period: 'last_30_days',
      selected_campaign_name: aiFeatureState.chat.selectedCampaignName || null,
      model: activeAiModel(),
      ai_preset: aiFeatureState.model.selectedPreset,
      options: {
        include_search_queries: true,
        include_dynamics: true,
        include_tracking: true,
        include_recommendations: true,
      },
    },
    aiService,
    onStart: () => {
      aiFeatureState.audit.loading = true;
      aiFeatureState.audit.error = '';
      render();
    },
    onSuccess: (job) => applyAiAuditJob(job),
    onError: (message) => { aiFeatureState.audit.error = message; },
    onFinally: () => {
      aiFeatureState.audit.loading = false;
      render();
    },
  });
  if (aiFeatureState.audit.job) scheduleAiAuditProgress(0);
}

async function refreshActiveAiAudit() {
  const jobId = aiFeatureState.audit.job?.job_id;
  if (!jobId || aiAuditRefreshInFlight || activeView !== 'ai') return;
  aiAuditRefreshInFlight = true;
  try {
    applyAiAuditJob(await aiService.fetchAiAuditJob(jobId));
  } catch (error) {
    aiFeatureState.audit.error = error.message || 'Не удалось обновить статус AI-аудита.';
  } finally {
    aiAuditRefreshInFlight = false;
    render();
  }
  const job = aiFeatureState.audit.job;
  if (job && !aiStore.isTerminalAiAuditStatus(job.status)) scheduleAiAuditProgress(job.poll_after_ms);
}

async function advanceActiveAiAudit(retry = false, compactRetry = false) {
  const jobId = aiFeatureState.audit.job?.job_id;
  if (!jobId || aiFeatureState.audit.loading || activeView !== 'ai') return;
  let pollOnlyAfterRequest = false;
  await advanceAiAuditJobFlow({
    jobId,
    retry,
    compactRetry,
    aiService,
    onStart: () => {
      aiFeatureState.audit.loading = true;
      aiFeatureState.audit.error = '';
      render();
      scheduleAiAuditProgress(1800, true);
    },
    onSuccess: (job) => applyAiAuditJob(job),
    onError: (message, error) => {
      const timeout = error?.code === 'ai_audit_generation_timeout'
        || error?.payload?.error_code === 'ai_audit_generation_timeout'
        || error?.name === 'AbortError'
        || /150 секунд|timeout/i.test(String(message || ''));
      pollOnlyAfterRequest = timeout;
      aiFeatureState.audit.error = timeout
        ? 'Этап продолжает выполняться на сервере. Проверяем статус задачи.'
        : message;
    },
    onFinally: () => {
      aiFeatureState.audit.loading = false;
      render();
    },
  });
  const job = aiFeatureState.audit.job;
  if (job && !aiStore.isTerminalAiAuditStatus(job.status)) {
    scheduleAiAuditProgress(job.poll_after_ms, pollOnlyAfterRequest);
  }
}

async function restoreAiAuditJob() {
  if (!selectedClientId || aiFeatureState.audit.loadedFor === selectedClientId) return;
  aiFeatureState.audit.loadedFor = selectedClientId;
  const jobId = window.localStorage.getItem(aiAuditStorageKey());
  if (!jobId) return;
  try {
    const job = await aiService.fetchAiAuditJob(jobId);
    applyAiAuditJob(job);
    render();
    if (!aiStore.isTerminalAiAuditStatus(job.status)) scheduleAiAuditProgress(job.poll_after_ms);
  } catch (error) {
    window.localStorage.removeItem(aiAuditStorageKey());
    aiFeatureState.audit.error = error.message || 'Не удалось восстановить AI-аудит.';
    render();
  }
}

async function cancelActiveAiAudit() {
  const jobId = aiFeatureState.audit.job?.job_id;
  if (!jobId) return;
  stopAiAuditPolling();
  try {
    applyAiAuditJob(await aiService.cancelAiAuditJob(jobId));
  } catch (error) {
    aiFeatureState.audit.error = error.message || 'Не удалось отменить AI-аудит.';
  }
  render();
}

async function resetAndRestartAiAudit() {
  const jobId = aiFeatureState.audit.job?.job_id;
  if (!jobId || aiFeatureState.audit.loading) return;
  stopAiAuditPolling();
  aiFeatureState.audit.loading = true;
  try {
    await aiService.resetAiAuditJob(jobId);
    persistAiAuditJob(null);
    aiFeatureState.audit = aiStore.createInitialAiAuditState();
    aiFeatureState.audit.loadedFor = selectedClientId;
    aiFeatureState.audit.loading = false;
    await startAiAudit('full_account');
  } catch (error) {
    aiFeatureState.audit.error = error.message || 'Не удалось завершить зависший аудит.';
  } finally {
    aiFeatureState.audit.loading = false;
    render();
  }
}

function clearActiveAiAudit() {
  stopAiAuditPolling();
  persistAiAuditJob(null);
  aiFeatureState.audit = aiStore.createInitialAiAuditState();
  aiFeatureState.audit.loadedFor = selectedClientId;
  render();
}


async function saveAiMemoryNote(note) {
  await saveAiMemoryNoteFlow({
    selectedClientId,
    note,
    businessContextService,
    onStart: (message) => {
      aiFeatureState.generation.memoryStatus = message;
    },
    onSuccess: (payload, message) => {
      businessContext = normalizeBusinessContext(payload);
      businessContextDraft = businessContext;
      aiFeatureState.generation.memoryStatus = message;
    },
    onError: (message) => {
      aiFeatureState.generation.memoryStatus = message;
    },
  });
}


async function loadAiStatus() {
  await loadAiStatusFlow({
    aiService,
    onStatus: (status) => {
      aiFeatureState.model.status = status;
    },
    onFinally: render,
  });
}


async function generateAiInsight(prompt) {
  const budget = activeAiBudget();
  await generateAiInsightFlow({
    prompt,
    aiService,
    model: activeAiModel(),
    maxTokens: budget.maxTokens,
    preset: aiFeatureState.model.selectedPreset,
    businessContext: businessContextForAi(),
    onStart: () => {
      aiFeatureState.generation.loading = true;
      aiFeatureState.generation.error = '';
      aiFeatureState.generation.result = null;
      render();
    },
    onSuccess: (result) => {
      aiFeatureState.generation.result = result;
    },
    onError: (message) => {
      aiFeatureState.generation.error = message;
    },
    onFinally: () => {
      aiFeatureState.generation.loading = false;
      render();
    },
  });
}


function pageContextSummary() {
  const client = currentClient();
  const dataStatus = hasPerformanceData() ? 'есть статистика' : 'статистика не загружена';
  const contextStatus = hasBusinessContextData(businessContext) ? 'контекст заполнен' : 'контекст не заполнен';
  return `Клиент: ${client.name || 'не выбран'}. Direct: ${client.directLogin || 'не подключен'}. Метрика: ${client.metricaCounter || 'не подключена'}. Данные: ${dataStatus}. Бизнес-контекст: ${contextStatus}.`;
}

function aiPromptFor(type) {
  const base = pageContextSummary();
  const prompts = {
    audit: `Проведи аудит рекламного проекта. ${base} Найди слабые места в структуре, целях, данных и объясни приоритеты действий.`,
    recommendations: `Сформируй практический план оптимизации Яндекс.Директа. ${base} Раздели рекомендации на быстрые правки, гипотезы и риски.`,
    report: `Подготовь управленческий отчёт для клиента. ${base} Опиши результаты, проблемы, следующие шаги и вопросы к клиенту.`,
    questions: `Составь список уточняющих вопросов к клиенту, чтобы улучшить аналитику и рекомендации. ${base}`,
    critical: `Найди критичные проблемы по выбранному клиенту. ${base} Сфокусируйся на расходе без конверсий по целям, высоком CPA, низком CTR и рисках трекинга.`,
    search_queries: `Проанализируй поисковые запросы. ${base} Найди нерелевантный интент, кандидатов в минус-слова и объясни риски исключения запросов.`,
    quick_wins: `Покажи quick wins по проекту. ${base} Дай короткий список действий, которые можно проверить без глубокой перестройки кампаний.`,
    yesterday: `Разбери вчерашний день по кампаниям. ${base} Не делай выводы о динамике, если нет данных для сравнения; сфокусируйся на расходе, CTR, CPA и конверсиях по целям.`,
  };
  return prompts[type] || prompts.audit;
}

function normalizeOptimizationPlan(payload) {
  return optimizationStore.normalizeOptimizationPlan(payload);
}

function normalizeOptimizationAction(action) {
  return optimizationStore.normalizeOptimizationAction(action);
}

function normalizeOptimizationPreview(payload) {
  return optimizationStore.normalizeOptimizationPreview(payload);
}

function getFilteredOptimizationActions() {
  return optimizationStore.getFilteredOptimizationActions(optimizationActions, optimizationActionFilter);
}

async function loadPerformanceSummary() {
  if (!selectedClientId || perfLoading) return;
  perfLoading = true;
  perfStatus = 'Загружаем сводку по кампаниям...';
  render();
  try {
    perfSummary = await performanceService.fetchPerformanceSummary(selectedClientId);
    perfStatus = 'Сводка обновлена.';
  } catch (error) {
    perfStatus = error.message || 'Не удалось загрузить сводку.';
  } finally {
    perfLoading = false;
    render();
  }
}

async function loadPerformanceRangeSummary() {
  if (!selectedClientId || performanceRangeState.loading) return;
  performanceRangeState.loading = true;
  performanceRangeState.status = 'Загружаем данные из Яндекс.Директа за выбранный период...';
  render();
  try {
    const summary = await performanceService.fetchPerformanceRangeSummary(selectedClientId, {
      preset: performanceRangeState.preset,
      dateFrom: performanceRangeState.dateFrom,
      dateTo: performanceRangeState.dateTo,
    });
    performanceRangeState.summary = summary;
    performanceRangeState.status = 'Данные за выбранный период загружены из Яндекс.Директа.';
    perfStatus = `Таблица кампаний обновлена: ${performancePeriodLabel(summary)}.`;
    performanceCampaignSearch = '';
  } catch (error) {
    performanceRangeState.status = error.message || 'Не удалось загрузить данные за выбранный период.';
  } finally {
    performanceRangeState.loading = false;
    render();
  }
}


async function loadBusinessContext(force = false) {
  if (!selectedClientId || businessContextLoading) return;
  if (!force && businessContextLoadedFor === selectedClientId) return;
  businessContextLoadedFor = selectedClientId;
  businessContextLoading = true;
  businessContextStatus = 'Загружаем контекст бизнеса...';
  render();
  try {
    const payload = await businessContextService.fetchBusinessContext(selectedClientId);
    businessContext = normalizeBusinessContext(payload);
    businessContextDraft = businessContext;
    businessContextStatus = hasBusinessContextData(businessContext) ? 'Контекст бизнеса загружен.' : 'Контекст пока пустой. Заполните основные поля.';
  } catch (error) {
    businessContext = businessContext || defaultBusinessContext();
    businessContextDraft = businessContext;
    businessContextStatus = error.message || 'Не удалось загрузить контекст бизнеса.';
  } finally {
    businessContextLoading = false;
    render();
  }
}


async function saveBusinessContext(form) {
  if (!selectedClientId) return;
  const draft = setBusinessContextDraftFromForm(form);
  businessContextSaving = true;
  businessContextStatus = 'Сохраняем контекст бизнеса...';
  render();
  try {
    const payload = await businessContextService.saveBusinessContext(selectedClientId, businessContextPayload(draft));
    businessContext = normalizeBusinessContext(payload);
    businessContextDraft = businessContext;
    businessContextStatus = 'Контекст бизнеса сохранён. AI будет использовать его в рекомендациях.';
  } catch (error) {
    businessContextStatus = error.message || 'Не удалось сохранить контекст бизнеса.';
  } finally {
    businessContextSaving = false;
    render();
  }
}


async function startSync() {
  if (!selectedClientId || !canRunSync() || syncLoading) return;
  syncLoading = true;
  syncStatusMessage = 'Запускаем синхронизацию с Директом и Метрикой...';
  render();
  try {
    void logJournalEvent(createSyncStatusJournalEvent({
      status: 'started',
      client: currentClient(),
      actor: currentJournalActor(),
      metadata: { directLogin: currentClient().directLogin || '' },
    }));
    const payload = await syncService.runClientSync(selectedClientId);
    syncStatusMessage = `Синхронизация запущена. Статус: ${syncJobStatusLabel(payload.status)}.`;
    void logJournalEvent(createSyncStatusJournalEvent({
      status: payload.status || 'started',
      client: currentClient(),
      actor: currentJournalActor(),
      entityId: payload.id || payload.job_id || null,
      metadata: { message: payload.message || syncStatusMessage },
    }));
    await loadClientsFromApi(true);
    await loadPerformanceSummary();
  } catch (error) {
    syncStatusMessage = error.message || 'Не удалось запустить синхронизацию.';
    void logJournalEvent(createSyncStatusJournalEvent({
      status: 'failed',
      client: currentClient(),
      actor: currentJournalActor(),
      severity: 'error',
      metadata: { message: syncStatusMessage },
    }));
  } finally {
    syncLoading = false;
    render();
  }
}


async function loadSyncJobs({ force = false } = {}) {
  const clientId = selectedClientId;
  if (!clientId) return;
  if (syncJobsLoading && syncJobsInFlightFor === clientId) return;
  const hasFreshJobs = syncJobsLoadedFor === clientId && Date.now() - syncJobsLastLoadedAt < SYNC_JOBS_REFRESH_MS;
  if (!force && hasFreshJobs) return;
  syncJobsLoading = true;
  syncJobsInFlightFor = clientId;
  render();
  try {
    const jobs = await syncService.fetchSyncJobs(clientId);
    if (selectedClientId === clientId) {
      syncJobs = jobs;
      syncJobsLoadedFor = clientId;
      syncJobsLastLoadedAt = Date.now();
    }
  } catch (error) {
    if (!syncStatusMessage) syncStatusMessage = error.message || 'История синхронизаций недоступна.';
  } finally {
    if (syncJobsInFlightFor === clientId) {
      syncJobsLoading = false;
      syncJobsInFlightFor = '';
    }
    render();
  }
}


async function loadOptimizationPlan() {
  await loadOptimizationPlanFlow({
    selectedClientId,
    loading: optimizationPlanLoading,
    optimizationService,
    onStart: (message) => {
      optimizationPlanLoading = true;
      optimizationStatus = message;
      render();
    },
    onSuccess: (plan, message) => {
      optimizationPlan = plan;
      optimizationStatus = message;
    },
    onError: (message) => {
      optimizationStatus = message;
    },
    onFinally: () => {
      optimizationPlanLoading = false;
      render();
    },
  });
}


async function loadOptimizationActions(force = false) {
  await loadOptimizationActionsFlow({
    selectedClientId,
    loading: optimizationActionsLoading,
    loadedFor: optimizationActionsLoadedFor,
    filter: optimizationActionFilter,
    force,
    optimizationService,
    onStart: (message) => {
      optimizationActionsLoading = true;
      optimizationActionsStatus = message;
      render();
    },
    onSuccess: (actions, loadedFor, message) => {
      optimizationActions = actions;
      optimizationActionsLoadedFor = loadedFor;
      optimizationActionsStatus = message;
    },
    onError: (message) => {
      optimizationActionsStatus = message;
    },
    onFinally: () => {
      optimizationActionsLoading = false;
      render();
    },
  });
}

async function createOptimizationDraftsFromPlan() {
  await createOptimizationDraftsFromPlanFlow({
    selectedClientId,
    loading: optimizationActionsLoading,
    optimizationService,
    onStart: (message) => {
      optimizationActionsLoading = true;
      optimizationActionsStatus = message;
      render();
    },
    onSuccess: (actions, loadedFor, message) => {
      optimizationActions = actions;
      optimizationActionsLoadedFor = loadedFor;
      optimizationActionsStatus = message;
    },
    onError: (message) => {
      optimizationActionsStatus = message;
    },
    onFinally: () => {
      optimizationActionsLoading = false;
      render();
    },
  });
}


async function updateOptimizationActionStatus(actionId, status, reviewerNote = '') {
  await updateOptimizationActionStatusFlow({
    selectedClientId,
    actionId,
    status,
    reviewerNote,
    actions: optimizationActions,
    optimizationService,
    onStart: (message) => {
      optimizationActionsStatus = message;
      render();
    },
    onSuccess: (actions, message) => {
      optimizationActions = actions;
      optimizationActionsStatus = message;
      const updatedAction = actions.find((action) => action.id === actionId) || { id: actionId, status };
      void logJournalEvent(createOptimizationActionStatusJournalEvent({
        action: updatedAction,
        status,
        actor: currentJournalActor(),
        metadata: { message },
      }));
    },
    onError: (message) => {
      optimizationActionsStatus = message;
    },
    onFinally: render,
  });
}

async function loadOptimizationExecutionPreview(actionId) {
  await loadOptimizationExecutionPreviewFlow({
    selectedClientId,
    actionId,
    currentPreview: optimizationExecutionPreviews[actionId],
    optimizationService,
    onStart: (targetActionId, data) => {
      optimizationExecutionPreviews = {
        ...optimizationExecutionPreviews,
        [targetActionId]: { loading: true, error: '', data },
      };
      render();
    },
    onSuccess: (targetActionId, preview) => {
      optimizationExecutionPreviews = {
        ...optimizationExecutionPreviews,
        [targetActionId]: { loading: false, error: '', data: preview },
      };
    },
    onError: (targetActionId, message) => {
      optimizationExecutionPreviews = {
        ...optimizationExecutionPreviews,
        [targetActionId]: { loading: false, error: message, data: null },
      };
    },
    onFinally: render,
  });
}


function renderMetricCards() {
  return `
    <div class="metricGrid">
      <article><span>Расход</span><strong>${formatMoney(spend)}</strong><small>за 30 дней</small></article>
      <article><span>Лиды</span><strong>${formatNumberSafe(leads)}</strong><small>средний CPL ${formatMoney(avgCpl)}</small></article>
      <article><span>ROMI</span><strong>${avgRoi}%</strong><small>выручка ${formatMoney(revenue)}</small></article>
      <article><span>AI-рекомендации</span><strong>${recommendations.length}</strong><small>готовы к проверке</small></article>
    </div>
  `;
}

function renderAudit() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">Аудит</span><h2>Найдено ${auditIssues.length} приоритетных задач</h2><p>AI группирует проблемы по влиянию на бюджет, конверсии и качество трафика.</p></div>
    <div class="issueList">${auditIssues.map((issue) => `<article class="issue ${issue.level}"><span>${issue.level}</span><h3>${issue.title}</h3><p>${issue.description}</p><strong>${issue.impact}</strong></article>`).join('')}</div>
  `);
}

function renderRecommendations() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">Рекомендации</span><h2>План оптимизации на неделю</h2><p>Каждая рекомендация содержит причину, ожидаемый эффект и уровень уверенности AI.</p></div>
    <div class="recommendationGrid">${recommendations.map((item) => `<article><div class="confidence">${item.confidence}%</div><h3>${item.title}</h3><p>${item.reason}</p><small>${item.effort}</small><button>Согласовать</button></article>`).join('')}</div>
  `);
}

function renderReports() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">Отчёты</span><h2>Черновик отчёта для клиента</h2><p>AI собирает результаты, выводы и следующий план работ в понятный отчёт.</p></div>
    <section class="reportPanel"><h3>${currentClientName()} — итоги месяца</h3><ul>${reportBullets.map((item) => `<li>${item}</li>`).join('')}</ul><button>Скачать PDF</button></section>
  `);
}

function renderAutopilot() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">Автопилот</span><h2>Правила безопасной автоматизации</h2><p>Вы контролируете, какие действия AI может применять автоматически, а какие только предлагать.</p></div>
    <div class="ruleList">${autopilotRules.map((rule) => `<article><div><h3>${rule.name}</h3><p>${rule.description}</p></div><label class="switch"><input type="checkbox" ${rule.enabled ? 'checked' : ''}/><span></span></label></article>`).join('')}</div>
  `);
}

function renderSyncCenter() {
  return `
    <section class="panel syncPanel">
      <div class="panelHeader">
        <div>
          <h3>Синхронизация данных</h3>
          <p>Загружаем кампании, расходы, цели и поисковые запросы из Яндекс.Директа и Метрики.</p>
        </div>
        <button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
      </div>
      <div class="syncStatusGrid">
        <article><span>Готовность</span><strong>${canRunSync() ? 'Можно запускать' : 'Нужен Direct login'}</strong></article>
        <article><span>Последний статус</span><strong>${syncJobStatusLabel(currentClient().syncStatus || 'never_synced')}</strong></article>
        <article><span>Данные кабинета</span><strong>${backendClientsAvailable ? 'API доступен' : 'локальный режим'}</strong></article>
      </div>
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
    </section>
  `;
}

function renderSyncDiagnosticsPanel(compact = false) {
  const client = currentClient();
  const issues = [];
  if (!client.id) issues.push(['Клиент', 'Создайте карточку клиента.']);
  if (!client.directLogin || client.directLogin === 'Не подключен') issues.push(['Direct login', 'Укажите логин Яндекс.Директа в карточке клиента.']);
  if (!client.metricaCounter || client.metricaCounter === 'Не подключен') issues.push(['Метрика', 'Укажите ID счётчика Метрики.']);
  if (!client.mainGoalId) issues.push(['Цель', 'Заполните основную цель, чтобы считать CPA.']);
  if (!getBoundYandexAccount() && !client.yandexAccountId) issues.push(['Привязка Яндекса', 'Выберите аккаунт из OAuth-доступов в разделе клиентов и интеграций.']);
  const hasProblems = issues.length > 0;
  return `
    <section class="panel diagnosticsPanel">
      <div class="panelHeader">
        <div>
          <h3>${compact ? 'Диагностика готовности' : 'Диагностика синхронизации'}</h3>
          <p>${hasProblems ? 'Что мешает корректной загрузке и анализу данных.' : 'Базовая конфигурация выглядит готовой.'}</p>
        </div>
        <span class="aiStatusBadge ${hasProblems ? 'pending' : 'ready'}">${hasProblems ? 'Нужны правки' : 'Готово'}</span>
      </div>
      ${hasProblems ? `
        <div class="issueList compactIssues">
          ${issues.map(([title, description]) => `<article class="issue medium"><span>fix</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></article>`).join('')}
        </div>
      ` : '<div class="authStatus integrationStatus">Можно запускать синхронизацию и строить AI-рекомендации.</div>'}
    </section>
  `;
}

function renderPerformanceTrendCharts(summary) {
  const daily = Array.isArray(summary?.daily) ? summary.daily : [];
  if (daily.length < 2) return '';
  const metrics = [
    ['cost', 'Расход', formatMoney],
    ['clicks', 'Клики', formatNumberSafe],
    ['goalConversions', 'Конверсии по целям', formatNumberSafe],
    ['ctr', 'CTR', formatPercent],
  ];
  const charts = metrics.map(([key, label, formatter]) => {
    const values = daily.map((item) => Number(item?.[key] || 0));
    const max = Math.max(...values, 0);
    const min = Math.min(...values, 0);
    const spread = Math.max(max - min, 1);
    const points = values.map((value, index) => {
      const x = daily.length === 1 ? 50 : (index / (daily.length - 1)) * 100;
      const y = 38 - ((value - min) / spread) * 30;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const lastValue = values.at(-1) || 0;
    return `
      <article class="kpi">
        <span>${escapeHtml(label)}</span>
        <strong>${formatter(lastValue)}</strong>
        <svg viewBox="0 0 100 42" role="img" aria-label="${escapeHtml(label)}" style="width:100%;height:42px;margin-top:8px;overflow:visible">
          <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
        </svg>
      </article>
    `;
  }).join('');
  return `<div class="kpiGrid periodTrendCharts">${charts}</div>`;
}
function renderYesterdaySummaryPanel() {
  const summary = performanceRangeState.summary;
  const totals = summary?.totals || {};
  const selectedGoals = summary?.selectedGoalIds?.length
    ? summary.selectedGoalIds.join(', ')
    : currentClient().conversionGoalIds || currentClient().mainGoalId || '';
  const presets = [
    ['today', 'Сегодня'],
    ['yesterday', 'Вчера'],
    ['3d', '3 дня'],
    ['7d', '7 дней'],
    ['14d', '14 дней'],
    ['30d', '30 дней'],
    ['this_month', 'Этот месяц'],
    ['custom', 'Свой период'],
  ];
  return `
    <section class="panel summaryPanel">
      <div class="panelHeader">
        <div>
          <h3>Сводка за период</h3>
          <p>${summary ? escapeHtml(performancePeriodLabel(summary)) : 'Выберите период и загрузите read-only отчёт из Яндекс.Директа.'}</p>
        </div>
        ${performanceRangeState.preset === 'custom' ? `<button class="secondaryButton" data-load-period-summary ${selectedClientId && !performanceRangeState.loading ? '' : 'disabled'}>${performanceRangeState.loading ? 'Загружаем...' : 'Загрузить данные'}</button>` : ''}
      </div>
      <div class="periodQuickControls" data-performance-period-controls>
        ${presets.map(([value, label]) => `<button class="${performanceRangeState.preset === value ? 'approveButton' : 'secondaryButton'}" type="button" data-period-preset="${escapeHtml(value)}">${escapeHtml(label)}</button>`).join('')}
      </div>
      ${performanceRangeState.preset === 'custom' ? `
        <div class="settingsRow">
          <label class="authField"><span>С даты</span><input type="date" data-period-from value="${escapeHtml(performanceRangeState.dateFrom)}" /></label>
          <label class="authField"><span>По дату</span><input type="date" data-period-to value="${escapeHtml(performanceRangeState.dateTo)}" /></label>
        </div>
      ` : ''}
      ${performanceRangeState.status ? `<div class="authStatus integrationStatus">${escapeHtml(performanceRangeState.status)}</div>` : ''}
      <div class="kpiGrid">
        <article class="kpi"><span>Кампаний</span><strong>${formatNumberSafe(summary?.campaigns?.length || 0)}</strong></article>
        <article class="kpi"><span>Показы</span><strong>${formatNumberSafe(totals.impressions || 0)}</strong></article>
        <article class="kpi"><span>Клики</span><strong>${formatNumberSafe(totals.clicks || 0)}</strong></article>
        <article class="kpi"><span>Расход</span><strong>${formatMoney(totals.cost || 0)}</strong></article>
        <article class="kpi"><span>CTR</span><strong>${formatPercent(totals.ctr || 0)}</strong></article>
        <article class="kpi"><span>CPC</span><strong>${formatMoney(totals.avgCpc || 0)}</strong></article>
        <article class="kpi"><span>Конверсии по целям</span><strong>${formatNumberSafe(totals.goalConversions || 0)}</strong></article>
        <article class="kpi"><span>CPA по целям</span><strong>${formatMoney(totals.goalCpa || 0)}</strong></article>
      </div>
      ${renderPerformanceTrendCharts(summary)}
      ${selectedGoals ? `<div class="authStatus integrationStatus"><strong>Цели:</strong> ${escapeHtml(selectedGoals)}</div>` : '<div class="authStatus integrationStatus">Укажите ID целей Метрики/Директа, чтобы считать CPA по целям.</div>'}
      ${!summary ? '<div class="authStatus integrationStatus">Данные за период ещё не загружены. Нажмите «Загрузить данные».</div>' : ''}
    </section>
  `;
}

function renderYandexDirectAuditPanel(compact = false) {
  const client = currentClient();
  const issues = [];
  if (!client.directLogin || client.directLogin === 'Не подключен') issues.push(['Нет логина Директа', 'AI не сможет связать клиента с рекламным аккаунтом.']);
  if (!client.metricaCounter || client.metricaCounter === 'Не подключен') issues.push(['Нет счётчика Метрики', 'Нельзя проверить цели и качество трафика.']);
  if (!client.mainGoalId) issues.push(['Нет основной цели', 'CPA и рекомендации будут неточными.']);
  if (perfSummary?.campaigns?.some((campaign) => Number(campaign.conversions || 0) === 0 && Number(campaign.cost || 0) > 0)) {
    issues.push(['Расход без конверсий', 'Есть кампании с расходом и нулевыми конверсиями.']);
  }
  if ((perfSummary?.searchQueryInsights?.candidateNegativeKeywords || 0) > 0) {
    issues.push(['Кандидаты в минус-слова', 'AI нашёл поисковые запросы для чистки трафика.']);
  }
  const visibleIssues = issues.length ? issues : [['Критичных проблем не найдено', 'После синхронизации AI покажет больше деталей по кампаниям и запросам.']];
  return `
    <section class="panel directAuditPanel">
      <div class="panelHeader">
        <div>
          <h3>${compact ? 'Быстрый аудит Директа' : 'Аудит Яндекс.Директа'}</h3>
          <p>Проверка готовности аккаунта к анализу и оптимизации.</p>
        </div>
        <span class="aiStatusBadge ${issues.length ? 'pending' : 'ready'}">${issues.length ? 'Есть задачи' : 'Ок'}</span>
      </div>
      <div class="issueList compactIssues">
        ${visibleIssues.map(([title, description]) => `<article class="issue ${issues.length ? 'medium' : 'low'}"><span>${issues.length ? 'fix' : 'ok'}</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></article>`).join('')}
      </div>
    </section>
  `;
}

function renderPerformanceSummaryPanel() {
  const tableSummary = performanceTableSummary();
  const campaignsData = tableSummary?.campaigns || [];
  const insights = tableSummary?.searchQueryInsights;
  const period = tableSummary?.period;
  const campaignName = (campaign, index = 0) => (
    campaign.name
    || campaign.campaignName
    || campaign.campaign_name
    || campaign.title
    || (campaign.campaign_id ? `Кампания ${campaign.campaign_id}` : `Кампания ${index + 1}`)
  );
  const campaignGoalConversions = (campaign) => campaign.goal_conversions ?? campaign.goalConversions ?? campaign.conversions_used ?? campaign.conversionsUsed ?? 0;
  const campaignGoalCpa = (campaign) => campaign.cpa_used ?? campaign.cpaUsed ?? campaign.goal_cpa ?? campaign.goalCpa ?? campaign.cpa ?? 0;
  const goals = tableSummary?.selectedGoalIds || [];
  const periodLabel = period?.from && period?.to ? `${period.from} — ${period.to}` : 'последняя синхронизация';
  return `
    <section class="panel performancePanel">
      <div class="panelHeader">
        <div>
          <h3>Сводка эффективности</h3>
          <p>Кампании за период ${escapeHtml(periodLabel)}. AI использует конверсии по выбранным целям${goals.length ? `: ${escapeHtml(goals.join(', '))}` : ''}.</p>
        </div>
      </div>
      ${campaignsData.length ? `
        <label class="authField compactSearchField">
          <span>Поиск по названию кампании или ID</span>
          <input data-performance-campaign-search value="${escapeHtml(performanceCampaignSearch)}" placeholder="Например: бренд, поиск, 119001..." autocomplete="off" />
        </label>
        <div class="dataTableWrap">
          <table class="dataTable">
            <thead><tr><th>Кампания</th><th>Показы</th><th>Клики</th><th>CTR</th><th>Расход</th><th>Конверсии по целям</th><th>CPA по целям</th></tr></thead>
            <tbody>${campaignsData.slice(0, 50).map((campaign, index) => `<tr data-performance-campaign-row data-search-text="${escapeHtml(`${campaignName(campaign, index)} ${campaign.campaign_id || ''}`.toLowerCase())}">
              <td><strong>${escapeHtml(campaignName(campaign, index))}</strong>${campaign.campaign_id ? `<br><small>ID: ${escapeHtml(campaign.campaign_id)}</small>` : ''}</td>
              <td>${formatNumberSafe(campaign.impressions || 0)}</td>
              <td>${formatNumberSafe(campaign.clicks || 0)}</td>
              <td>${formatPercent(campaign.ctr || 0)}</td>
              <td>${formatMoney(campaign.cost || 0)}</td>
              <td>${formatNumberSafe(campaignGoalConversions(campaign))}</td>
              <td>${formatMoney(campaignGoalCpa(campaign))}</td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
        <div class="authStatus integrationStatus" data-performance-search-empty hidden>По такому запросу кампании не найдены.</div>
        ${campaignsData.length > 50 ? `<div class="authStatus integrationStatus">Показано 50 из ${formatNumberSafe(campaignsData.length)} кампаний. Используйте поиск, чтобы сузить список.</div>` : ''}
      ` : '<div class="authStatus integrationStatus">Кампаний пока нет. Нужна синхронизация.</div>'}
      ${insights ? `
        <div class="insightGrid">
          <article><span>Запросов</span><strong>${formatNumberSafe(insights.totalQueries || 0)}</strong></article>
          <article><span>Кандидатов в минус-слова</span><strong>${formatNumberSafe(insights.candidateNegativeKeywords || 0)}</strong></article>
          <article><span>Расход на нерелевантное</span><strong>${formatMoney(insights.wastedSpend || 0)}</strong></article>
        </div>
      ` : ''}
    </section>
  `;
}

function businessContextPageContext(compact = false) {
  const context = businessContextDraft || businessContext || defaultBusinessContext();
  return {
    selectedClientId,
    selectedClient: currentClient(),
    businessContext,
    businessContextDraft,
    businessContextLoading,
    businessContextSaving,
    businessContextStatus,
    compact,
    context,
    score: contextCompletenessScore(context),
    copyText: businessContextCopyText(context),
    escapeHtml,
  };
}

function renderBusinessContextPanel(compact = false) {
  return renderBusinessContextPanelContent(businessContextPageContext(compact));
}

function renderBusinessContext() {
  const contentRenderer = resolvePageContentRenderer('business-context');

  if (typeof contentRenderer !== 'function') {
    return renderShell(renderBusinessContextPanel());
  }

  return renderShell(contentRenderer(businessContextPageContext(false)));
}

function renderProjectDiagnostics() {
  const client = currentClient();
  const hasClient = Boolean(client.id);
  const readiness = getReadinessState();
  const nextAction = getNextBestAction();
  const readyCount = readiness.filter((item) => item.status === 'ready').length;
  return renderShell(`
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Следующий шаг</h3>
          <p>${escapeHtml(nextAction.description || nextAction.label || '')}</p>
        </div>
        <span class="aiStatusBadge ${badgeClassForStatus(nextAction.status)}">${escapeHtml(compactStatusLabel(nextAction.status))}</span>
      </div>
      <div class="nextStepFocus"><span>Сейчас важнее всего</span><strong>${escapeHtml(nextAction.nextAction)}</strong></div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Готовность</span><strong>${formatNumberSafe(readyCount)} / ${formatNumberSafe(readiness.length)}</strong></article>
        <article class="kpi blue"><span>Клиент</span><strong>${hasClient ? 'Готово' : 'Нужно действие'}</strong></article>
        <article class="kpi orange"><span>Данные</span><strong>${hasPerformanceData() ? 'Готово' : 'Нет данных'}</strong></article>
        <article class="kpi orange"><span>Минус-слова</span><strong>${formatNumberSafe(perfSummary?.searchQueryInsights?.candidateNegativeKeywords || 0)}</strong></article>
      </div>
      <div class="heroActions">
        ${renderActionButton('Перейти к шагу', `data-go-view="${escapeHtml(nextAction.targetView || 'clients')}"`, 'primary')}
        ${renderActionButton(syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию', `data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}`)}
        ${renderActionButton('Клиенты и интеграции', 'data-go-view="clients"')}
      </div>
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
    </section>
    ${renderReadinessPanel(readiness, nextAction)}
    ${renderSyncCenter()}
    ${renderSyncDiagnosticsPanel(false)}
    ${renderYandexDirectAuditPanel(true)}
    ${renderBusinessContextPanel(true)}
  `);
}

function renderDashboard() {
  const client = currentClient();
  const hasClient = Boolean(client.id);
  const readiness = getReadinessState();
  const nextAction = getNextBestAction();
  const readyCount = readiness.filter((item) => item.status === 'ready').length;
  const contentRenderer = resolvePageContentRenderer('dashboard');

  if (typeof contentRenderer !== 'function') {
    return renderDashboardViaPageModule();
  }

  return renderShell(contentRenderer({
    clientName: client.name,
    hasClient,
    readiness,
    nextAction,
    readyCount,
    readinessLength: readiness.length,
    nextTarget: nextAction.targetView || 'dashboard',
    hasPerformanceData: hasPerformanceData(),
    candidateNegativeKeywords: perfSummary?.searchQueryInsights?.candidateNegativeKeywords || 0,
    syncLoading,
    canRunSync: canRunSync(),
    syncStatusMessage,
    renderActionButton,
    renderReadinessPanel,
    renderSyncCenter,
    renderBusinessContextPanel,
    renderSyncDiagnosticsPanel,
    renderYesterdaySummaryPanel,
    renderYandexDirectAuditPanel,
    renderPerformanceSummaryPanel,
    formatNumberSafe,
    badgeClassForStatus,
    compactStatusLabel,
    escapeHtml,
  }));
}

function renderDashboardViaPageModule() {
  const renderer = resolvePageRenderer('dashboard');

  if (!renderer) {
    return renderDashboard();
  }

  return renderer({
    legacyRenderDashboard: renderDashboard,
  });
}

function renderClients() {
  const contentRenderer = resolvePageContentRenderer('clients');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">👥 Клиенты</span><h2>Клиенты временно недоступны</h2><p>Модуль клиентов не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(`
    ${contentRenderer({
      selectedClientId,
      accountClients,
      backendClientsAvailable,
      backendClientsStatus,
      clientFormStatus,
      clientDraftName,
      clientDraftDirectLogin,
      clientDraftMetricaCounter,
      selectedClient: currentClient(),
      clientSettingsDraft,
      clientSettingsSaving,
      clientSettingsStatus,
      escapeHtml,
    })}
    ${renderClientIntegrationsSection()}
  `);
}

function renderClientIntegrationsSection() {
  const contentRenderer = resolvePageContentRenderer('integrations');

  if (typeof contentRenderer !== 'function') {
    return `
      <div class="pageIntro"><span class="eyebrow">Интеграции клиента</span><h2>Интеграции временно недоступны</h2><p>Модуль интеграций не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `;
  }

  return `
    ${contentRenderer(integrationsPageContext())}
  `;
}

function integrationsPageContext() {
  return {
    selectedClientId,
    selectedClient: currentClient(),
    integrationStatus,
    clientYandexIntegration,
    clientYandexStatus,
    clientYandexLoading,
    apiBaseDraft,
    escapeHtml,
  };
}

function renderIntegrations() {
  activeView = 'clients';
  return renderClients();
}

function aiAssistantPageContext() {
  const budget = activeAiBudget();
  return createAiAssistantPageContext({
    selectedClientId,
    selectedClient: currentClient(),
    aiStatus: aiFeatureState.model.status,
    selectedAiModel: aiFeatureState.model.selectedModel,
    customAiModel: aiFeatureState.model.customModel,
    customModelValue: CUSTOM_MODEL_VALUE,
    selectedAiPreset: aiFeatureState.model.selectedPreset,
    aiResolvedMaxTokens: budget.maxTokens,
    aiMaxTokensMode: aiFeatureState.model.maxTokensMode,
    aiToolResultsMode: aiFeatureState.model.toolResultsMode,
    aiChatHistoryLimit: aiFeatureState.model.chatHistoryLimit,
    aiSearchQueryLimit: aiFeatureState.model.searchQueryLimit,
    aiCompactContext: aiFeatureState.model.compactContext,
    aiPromptDebugLoading: aiFeatureState.generation.promptDebugLoading,
    aiPromptDebugError: aiFeatureState.generation.promptDebugError,
    aiPromptDebug: aiFeatureState.generation.promptDebug,
    campaignOptions: campaignOptions(),
    aiChatSelectedCampaignName: aiFeatureState.chat.selectedCampaignName,
    aiChatMessages: aiFeatureState.chat.messages,
    aiChatInput: aiFeatureState.chat.input,
    aiChatLoading: aiFeatureState.chat.loading,
    aiChatError: aiFeatureState.chat.error,
    aiChatErrorDetails: aiFeatureState.chat.errorDetails,
    aiChatToolTraces: aiFeatureState.chat.toolTraces,
    aiRecommendationsLoading: aiFeatureState.generation.recommendationsLoading,
    aiRecommendationsError: aiFeatureState.generation.recommendationsError,
    clientAiRecommendations: aiFeatureState.generation.clientRecommendations,
    aiLoading: aiFeatureState.generation.loading,
    aiError: aiFeatureState.generation.error,
    aiResult: aiFeatureState.generation.result,
    performanceSummary: perfSummary,
    businessContext,
    optimizationActions,
    aiAuditJob: aiFeatureState.audit.job,
    aiAuditLoading: aiFeatureState.audit.loading,
    aiAuditError: aiFeatureState.audit.error,
    formatNumberSafe,
    escapeHtml,
  });
}

function renderAiAssistant() {
  const contentRenderer = resolvePageContentRenderer('ai');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">AI-аналитик</span><h2>AI workspace временно недоступен</h2><p>Модуль AI-аналитика не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(contentRenderer(aiAssistantPageContext()));
}

function settingsPageContext() {
  const budget = activeAiBudget();
  return {
    currentEmail,
    apiBaseDraft,
    apiBase: API_BASE,
    backendClientsAvailable,
    aiStatus: aiFeatureState.model.status,
    selectedAiModel: aiFeatureState.model.selectedModel,
    selectedAiPreset: aiFeatureState.model.selectedPreset,
    aiResolvedMaxTokens: budget.maxTokens,
    aiMaxTokensMode: aiFeatureState.model.maxTokensMode,
    aiToolResultsMode: aiFeatureState.model.toolResultsMode,
    aiChatHistoryLimit: aiFeatureState.model.chatHistoryLimit,
    aiSearchQueryLimit: aiFeatureState.model.searchQueryLimit,
    aiCompactContext: aiFeatureState.model.compactContext,
    escapeHtml,
  };
}

function renderSettings() {
  const contentRenderer = resolvePageContentRenderer('settings');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">Настройки</span><h2>Настройки временно недоступны</h2><p>Модуль настроек не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(contentRenderer(settingsPageContext()));
}

function optimizationPageContext() {
  return {
    selectedClientId,
    selectedClient: currentClient(),
    performanceSummary: perfSummary,
    optimizationPlan,
    optimizationPlanLoading,
    optimizationStatus,
    optimizationActions,
    optimizationActionsLoading,
    optimizationActionsStatus,
    optimizationActionFilter,
    optimizationExecutionPreviews,
    getFilteredOptimizationActions,
    normalizeDate,
    formatNumberSafe,
    formatPercent,
    formatMoney,
    compactStatusLabel,
    escapeHtml,
  };
}

function renderOptimization() {
  const contentRenderer = resolvePageContentRenderer('optimization');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">Оптимизация</span><h2>Оптимизация временно недоступна</h2><p>Модуль оптимизации не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(contentRenderer(optimizationPageContext()));
}

function wordstatPageContext() {
  return {
    selectedClientId,
    selectedClient: currentClient(),
    escapeHtml,
  };
}

function renderWordstat() {
  const contentRenderer = resolvePageContentRenderer('wordstat');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">Wordstat</span><h2>Wordstat временно недоступен</h2><p>Модуль Wordstat не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(contentRenderer(wordstatPageContext()));
}

function journalPageContext() {
  return {
    selectedClientId,
    selectedClient: currentClient(),
    journalState,
    escapeHtml,
  };
}

function renderJournal() {
  const contentRenderer = resolvePageContentRenderer('journal');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">Журнал</span><h2>Журнал временно недоступен</h2><p>Модуль Journal не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(contentRenderer(journalPageContext()));
}

function journalFiltersWithClient(filters = {}) {
  return {
    ...filters,
    clientId: selectedClientId || null,
    cursor: null,
  };
}

function readJournalFilters() {
  const fields = app.querySelectorAll('[data-journal-filters] input[name], [data-journal-filters] select[name], [data-journal-filters] textarea[name]');
  const filters = {};
  fields.forEach((field) => {
    filters[field.name] = field.value;
  });
  return journalFiltersWithClient(filters);
}

function readJournalCreateInput(event) {
  const form = event?.target?.closest?.('[data-journal-create-form]');
  if (!form) return {};
  const formData = new FormData(form);
  return createJournalEntryPayload({
    scope: selectedClientId ? 'client' : 'system',
    clientId: selectedClientId || null,
    source: formData.get('source'),
    category: formData.get('category'),
    type: formData.get('type'),
    severity: formData.get('severity'),
    title: formData.get('title'),
    summary: formData.get('summary'),
    actor: { kind: 'user', id: currentEmail, label: currentEmail || 'User' },
  });
}

function resetJournalFilters() {
  journalState.filters = createDefaultJournalFilters({ clientId: selectedClientId || null });
  journalState.nextCursor = null;
  journalLoadedFor = '';
  render();
}

async function loadJournalEntries(filters = journalState.filters) {
  await loadJournalEntriesFlow({
    state: journalState,
    source: journalSource,
    filters: journalFiltersWithClient(filters),
    onSuccess: () => {
      journalLoadedFor = selectedClientId || 'system';
    },
    render,
  });
}

async function loadMoreJournalEntries() {
  await loadMoreJournalEntriesFlow({
    state: journalState,
    source: journalSource,
    render,
  });
}

async function createJournalEntry(input = {}) {
  await createJournalEntryFlow({
    state: journalState,
    source: journalSource,
    input: {
      ...input,
      scope: selectedClientId ? 'client' : input.scope || 'system',
      clientId: selectedClientId || input.clientId || null,
    },
    onSuccess: () => {
      journalLoadedFor = selectedClientId || 'system';
    },
    render,
  });
}

async function refreshJournal() {
  await refreshJournalFlow({
    state: journalState,
    source: journalSource,
    filters: journalFiltersWithClient(journalState.filters),
    onSuccess: () => {
      journalLoadedFor = selectedClientId || 'system';
    },
    render,
  });
}

const journalEventHandlers = createJournalEventHandlers({
  state: journalState,
  readFilters: readJournalFilters,
  readCreateInput: readJournalCreateInput,
  loadEntries: loadJournalEntries,
  loadMore: loadMoreJournalEntries,
  createEntry: createJournalEntry,
  refresh: refreshJournal,
  resetFilters: resetJournalFilters,
  render,
});


function render() {
  activeView = normalizeAppView(activeView);
  if (activeView !== 'ai') stopAiAuditPolling();
  const views = {
    landing: renderLanding,
    login: renderLogin,
    dashboard: renderDashboardViaPageModule,
    diagnostics: renderProjectDiagnostics,
    clients: renderClients,
    'business-context': renderBusinessContext,
    audit: renderAudit,
    recommendations: renderRecommendations,
    ai: renderAiAssistant,
    reports: renderReports,
    autopilot: renderAutopilot,
    integrations: renderIntegrations,
    optimization: renderOptimization,
    wordstat: renderWordstat,
    journal: renderJournal,
    settings: renderSettings,
  };
  const renderView = views[activeView] || renderDashboard;
  app.innerHTML = renderView();
  document.body.dataset.view = activeView;
  if (activeView === 'login') {
    const emailInput = app.querySelector('input[name="email"]');
    if (emailInput) emailInput.value = authEmail;
  }
  const isClientWorkspaceView = activeView === 'clients' || activeView === 'integrations';
  if (isClientWorkspaceView && !integrationStatus.message && integrationStatus.connected === undefined) {
    loadIntegrationStatus();
  }
  if (isClientWorkspaceView && selectedClientId) {
    loadClientYandexIntegration();
  }
  if (activeView === 'dashboard' && selectedClientId) {
    if (!perfSummary && !perfLoading) loadPerformanceSummary();
    if (!clientYandexIntegration && !clientYandexLoading) loadClientYandexIntegration();
    if (!businessContext && !businessContextLoading && businessContextLoadedFor !== selectedClientId) loadBusinessContext();
  }
  if (activeView === 'diagnostics' && selectedClientId) {
    if (!perfSummary && !perfLoading) loadPerformanceSummary();
    if (!clientYandexIntegration && !clientYandexLoading) loadClientYandexIntegration();
    if (!businessContext && !businessContextLoading && businessContextLoadedFor !== selectedClientId) loadBusinessContext();
  }
  if (activeView === 'business-context' && selectedClientId && !businessContextLoading && businessContextLoadedFor !== selectedClientId) {
    loadBusinessContext();
  }
  if (activeView === 'recommendations' && selectedClientId && !perfSummary && !perfLoading) {
    loadPerformanceSummary();
  }
  if (activeView === 'optimization' && selectedClientId) {
    if (!perfSummary && !perfLoading) loadPerformanceSummary();
    if (!optimizationPlan && !optimizationPlanLoading) loadOptimizationPlan();
    if (optimizationActionsLoadedFor !== selectedClientId && !optimizationActionsLoading) loadOptimizationActions();
  }
  if ((activeView === 'ai' || activeView === 'settings') && aiFeatureState.model.status.message === 'Статус OpenRouter ещё не загружен.') {
    loadAiStatus();
  }
  if (activeView === 'ai' && selectedClientId && !businessContextLoading && businessContextLoadedFor !== selectedClientId) {
    loadBusinessContext();
  }
  if (activeView === 'ai' && selectedClientId) {
    void restoreAiAuditJob();
  }
  if (activeView === 'journal' && (selectedClientId || !journalState.loading)) {
    const expectedJournalKey = selectedClientId || 'system';
    if (journalLoadedFor !== expectedJournalKey && !journalState.loading) loadJournalEntries();
  }
  if (aiChatShouldScrollToBottom) {
    window.requestAnimationFrame(scrollAiChatToBottom);
  }
  if (activeView !== 'landing' && activeView !== 'login') {
    loadClientsFromApi();
  }
}

let routeRenderTimer = 0;

function scheduleRouteRender(routeId) {
  if (page !== 'app') return;
  const nextView = normalizeAppView(routeId);
  if (activeView === nextView) return;
  activeView = nextView;
  if (routeRenderTimer) window.clearTimeout(routeRenderTimer);
  routeRenderTimer = window.setTimeout(() => {
    routeRenderTimer = 0;
    render();
  }, 0);
}

window.addEventListener('directpilot:route-change', (event) => {
  scheduleRouteRender(event.detail?.routeId);
});

window.addEventListener('hashchange', () => {
  scheduleRouteRender(window.location.hash || 'dashboard');
});

app.addEventListener('input', (event) => {
  const authInput = event.target.closest('input[name="email"], input[name="code"]');
  if (authInput?.name === 'email') authEmail = authInput.value;
  if (authInput?.name === 'code') authCode = authInput.value;
  if (event.target.matches('[data-client-form] input')) {
    const form = event.target.closest('[data-client-form]');
    if (form) {
      const formData = new FormData(form);
      clientDraftName = formData.get('name')?.toString() || '';
      clientDraftDirectLogin = formData.get('directLogin')?.toString() || '';
      clientDraftMetricaCounter = formData.get('metricaCounter')?.toString() || '';
    }
  }
  if (event.target.matches('[data-ai-chat-form] textarea[name="message"]')) {
    aiFeatureState.chat.input = event.target.value;
  }
  handleAiInputEvent(event, {
    setCustomModel: (value) => {
      aiFeatureState.model.customModel = value;
    },
    setSearchQueryLimit: (value) => {
      aiFeatureState.model.searchQueryLimit = value;
      saveAiModelSettings();
    },
  });
  if (event.target.matches('[data-business-context-form] textarea')) {
    const form = event.target.closest('[data-business-context-form]');
    if (form) setBusinessContextDraftFromForm(form);
  }
  if (event.target.matches('[data-client-settings-form] input, [data-client-settings-form] textarea')) {
    const form = event.target.closest('[data-client-settings-form]');
    if (form) setClientSettingsDraftFromForm(form);
  }
  if (event.target.matches('[data-performance-campaign-search]')) {
    performanceCampaignSearch = event.target.value;
    const search = performanceCampaignSearch.trim().toLowerCase();
    const rows = [...app.querySelectorAll('[data-performance-campaign-row]')];
    let visibleRows = 0;
    rows.forEach((row) => {
      const isVisible = !search || String(row.dataset.searchText || '').includes(search);
      row.hidden = !isVisible;
      if (isVisible) visibleRows += 1;
    });
    const empty = app.querySelector('[data-performance-search-empty]');
    if (empty) empty.hidden = !search || visibleRows > 0;
  }
  if (event.target.matches('[data-period-from]')) {
    performanceRangeState.dateFrom = event.target.value;
  }
  if (event.target.matches('[data-period-to]')) {
    performanceRangeState.dateTo = event.target.value;
  }
});

app.addEventListener('change', (event) => {
  if (event.target.closest('[data-journal-filters]')) {
    journalEventHandlers.handleJournalChangeEvent(event);
    return;
  }
  if (handleAiChangeEvent(event, {
    customModelValue: CUSTOM_MODEL_VALUE,
    setModel: (value, customValue) => {
      aiFeatureState.model.selectedModel = aiStore.normalizeProductionAiModel(value);
      if (customValue !== undefined) aiFeatureState.model.customModel = customValue;
      saveAiModelSettings();
    },
    setPreset: (value) => {
      aiFeatureState.model.selectedPreset = value;
      saveAiModelSettings();
    },
    setMaxTokensMode: (value) => {
      aiFeatureState.model.maxTokensMode = value;
      saveAiModelSettings();
    },
    setToolResultsMode: (value) => {
      aiFeatureState.model.toolResultsMode = value;
      saveAiModelSettings();
    },
    setChatHistoryLimit: (value) => {
      aiFeatureState.model.chatHistoryLimit = value;
      saveAiModelSettings();
    },
    setCompactContext: (value) => {
      aiFeatureState.model.compactContext = value;
      saveAiModelSettings();
    },
    setChatCampaign: (value) => {
      aiFeatureState.chat.selectedCampaignName = value;
    },
    render,
  })) return;
  if (event.target.matches('[data-optimization-action-filter]')) {
    optimizationActionFilter = event.target.value;
    optimizationActionsLoadedFor = '';
    loadOptimizationActions(true);
  }
});

function getEditableFieldTarget(target) {
  const editable = target?.closest?.('input, textarea, select, [contenteditable="true"]');
  if (editable) return editable;
  const label = target?.closest?.('label');
  return label?.querySelector?.('input, textarea, select, [contenteditable="true"]') || null;
}

const CABINET_ACTION_CLICK_SELECTOR = [
  '[data-journal-apply-filters]',
  '[data-journal-reset-filters]',
  '[data-journal-refresh]',
  '[data-journal-load-more]',
  '[data-logout]',
  '[data-auth-back]',
  '[data-open-settings]',
  '[data-profile-toggle]',
  '[data-client-menu-toggle]',
  '[data-client-id]',
  '[data-select-client]',
  '[data-sync-client]',
  '[data-load-performance]',
  '[data-load-optimization-plan]',
  '[data-load-optimization-actions]',
  '[data-create-optimization-drafts]',
  '[data-update-optimization-action]',
  '[data-preview-optimization-action]',
  '[data-refresh-client-yandex]',
  '[data-bind-yandex-account]',
  '[data-unbind-yandex]',
  '[data-delete-yandex-account]',
  '[data-reset-business-context]',
  '[data-copy-text]',
  '[data-reset-client-settings]',
  '[data-delete-client]',
  '[data-ai-prompt-debug]',
  '[data-client-ai-recommendations]',
  '[data-ai-chat-sample]',
  '[data-ai-prompt]',
  '[data-ai-audit-start]',
  '[data-ai-audit-cancel]',
  '[data-ai-audit-retry]',
  '[data-ai-audit-compact-retry]',
  '[data-ai-audit-new]',
  '[data-ai-audit-open]',
  '[data-integration="yandex-direct"]',
  '[data-period-preset]',
  '[data-load-period-summary]',
].join(',');

function getCabinetActionClickTarget(target) {
  return target?.closest?.(CABINET_ACTION_CLICK_SELECTOR) || null;
}

function getRouteClickTarget(target) {
  return target?.closest?.('button[data-view], a[data-view], button[data-go-view], a[data-go-view], [role="button"][data-view], [role="button"][data-go-view]') || null;
}

async function handleCabinetActionClick(event) {
  if (event.target.closest('[data-journal-apply-filters], [data-journal-reset-filters], [data-journal-refresh], [data-journal-load-more]')) {
    await journalEventHandlers.handleJournalClickEvent(event);
    return true;
  }
  if (event.target.closest('[data-logout]')) {
    stopAiAuditPolling();
    clearSession();
    window.location.href = 'login.html';
    return true;
  }
  if (event.target.closest('[data-auth-back]')) {
    authStep = 'email';
    authStatus = '';
    authCode = '';
    render();
    return true;
  }
  if (event.target.closest('[data-open-settings]')) {
    activeView = 'settings';
    render();
    return true;
  }
  if (event.target.closest('[data-client-menu-toggle]')) {
    const menu = app.querySelector('[data-client-menu]');
    if (menu) menu.hidden = !menu.hidden;
    return true;
  }
  if (event.target.closest('[data-profile-toggle]')) {
    const panel = app.querySelector('[data-profile-panel]');
    if (panel) panel.hidden = !panel.hidden;
    return true;
  }
  const clientButton = event.target.closest('[data-client-id], [data-select-client]');
  if (clientButton) {
    selectedClientId = clientButton.dataset.clientId || clientButton.dataset.selectClient;
    saveSelectedClientId(selectedClientId);
    resetClientScopedUiState({ nextActiveView: activeView });
    void logJournalEvent(createClientSelectedJournalEvent({
      client: currentClient(),
      actor: currentJournalActor(),
    }));
    render();
    return true;
  }
  if (event.target.closest('[data-sync-client]')) {
    await startSync();
    return true;
  }
  if (event.target.closest('[data-load-performance]')) {
    await loadPerformanceSummary();
    return true;
  }
  const periodPresetButton = event.target.closest('[data-period-preset]');
  if (periodPresetButton) {
    performanceRangeState.preset = periodPresetButton.dataset.periodPreset || 'yesterday';
    performanceRangeState.status = '';
    performanceRangeState.summary = null;
    performanceCampaignSearch = '';
    render();
    if (performanceRangeState.preset !== 'custom') {
      await loadPerformanceRangeSummary();
    }
    return true;
  }
  if (event.target.closest('[data-load-period-summary]')) {
    await loadPerformanceRangeSummary();
    return true;
  }
  if (event.target.closest('[data-load-optimization-plan]')) {
    await loadOptimizationPlan();
    return true;
  }
  if (event.target.closest('[data-load-optimization-actions]')) {
    await loadOptimizationActions(true);
    return true;
  }
  if (event.target.closest('[data-create-optimization-drafts]')) {
    await createOptimizationDraftsFromPlan();
    return true;
  }
  const updateActionButton = event.target.closest('[data-update-optimization-action]');
  if (updateActionButton) {
    await updateOptimizationActionStatus(updateActionButton.dataset.updateOptimizationAction, updateActionButton.dataset.status);
    return true;
  }
  const previewActionButton = event.target.closest('[data-preview-optimization-action]');
  if (previewActionButton) {
    await loadOptimizationExecutionPreview(previewActionButton.dataset.previewOptimizationAction);
    return true;
  }
  if (event.target.closest('[data-refresh-client-yandex]')) {
    await loadClientYandexIntegration(true);
    return true;
  }
  const bindYandexButton = event.target.closest('[data-bind-yandex-account]');
  if (bindYandexButton) {
    await bindClientYandexAccount(bindYandexButton.dataset.bindYandexAccount);
    return true;
  }
  if (event.target.closest('[data-unbind-yandex]')) {
    await unbindClientYandexAccount();
    return true;
  }
  const deleteYandexButton = event.target.closest('[data-delete-yandex-account]');
  if (deleteYandexButton) {
    await deleteYandexAccount(deleteYandexButton.dataset.deleteYandexAccount);
    return true;
  }
  if (event.target.closest('[data-reset-business-context]')) {
    businessContextDraft = businessContext || defaultBusinessContext();
    render();
    return true;
  }
  const copyButton = event.target.closest('[data-copy-text]');
  if (copyButton) {
    await navigator.clipboard?.writeText(copyButton.dataset.copyText || '');
    return true;
  }
  if (event.target.closest('[data-reset-client-settings]')) {
    clientSettingsDraft = null;
    render();
    return true;
  }
  const deleteButton = event.target.closest('[data-delete-client]');
  if (deleteButton) {
    await deleteClient(deleteButton.dataset.deleteClient);
    return true;
  }
  const auditStartButton = event.target.closest('[data-ai-audit-start]');
  if (auditStartButton) {
    await startAiAudit(auditStartButton.dataset.aiAuditStart || 'full_account');
    return true;
  }
  if (event.target.closest('[data-ai-audit-cancel]')) {
    await cancelActiveAiAudit();
    return true;
  }
  if (event.target.closest('[data-ai-audit-retry]')) {
    await advanceActiveAiAudit(true);
    return true;
  }
  if (event.target.closest('[data-ai-audit-compact-retry]')) {
    await advanceActiveAiAudit(false, true);
    return true;
  }
  if (event.target.closest('[data-ai-audit-reset]')) {
    await resetAndRestartAiAudit();
    return true;
  }
  if (event.target.closest('[data-ai-audit-new]')) {
    clearActiveAiAudit();
    return true;
  }
  if (event.target.closest('[data-ai-audit-open]')) {
    app.querySelector('[data-ai-audit-panel]')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return true;
  }
  if (await handleAiClickEvent(event, {
    loadPromptDebug: loadAiPromptDebug,
    requestRecommendations: requestAiRecommendations,
    setChatInput: (value) => {
      aiFeatureState.chat.input = value;
    },
    generateInsight: generateAiInsight,
    promptFor: aiPromptFor,
    render,
  })) return true;
  const integrationButton = event.target.closest('[data-integration="yandex-direct"]');
  if (integrationButton) {
    await startYandexOAuthFlow({
      integrationsService,
      onStart: (message) => {
        integrationStatus.message = message;
        render();
      },
      onRedirect: (authUrl) => {
        window.location.href = authUrl;
      },
      onError: (message) => {
        integrationStatus = { ...integrationStatus, message };
        render();
      },
    });
    return true;
  }
  return false;
}

document.addEventListener('click', (event) => {
  const actionTarget = getCabinetActionClickTarget(event.target);
  if (!actionTarget || app.contains(actionTarget) || getEditableFieldTarget(event.target)) {
    return;
  }
  event.preventDefault();
  void handleCabinetActionClick(event).catch((error) => {
    console.error('DirectPilot action failed', error);
  });
}, true);

app.addEventListener('submit', async (event) => {
  if (event.target.closest('[data-journal-create-form]')) {
    await journalEventHandlers.handleJournalSubmitEvent(event);
    return;
  }
  const authForm = event.target.closest('[data-auth-form]');
  if (authForm) {
    event.preventDefault();
    authLoading = true;
    authStatus = '';
    render();
    try {
      if (authStep === 'email') {
        const email = new FormData(authForm).get('email');
        authEmail = email;
        await requestEmailCode(email);
        window.localStorage.setItem('directpilot_auth_email', email);
        authStep = 'code';
        authStatus = 'Код отправлен на email.';
      } else {
        const code = new FormData(authForm).get('code');
        const data = await verifyEmailCode(authEmail, code);
        const sessionToken = data.session_token || data.access_token;
        const sessionEmail = data.email || authEmail;
        saveSession(sessionToken, sessionEmail);
        window.location.href = 'app.html';
      }
    } catch (error) {
      authStatus = error.message;
    } finally {
      authLoading = false;
      render();
    }
    return;
  }

  const apiForm = event.target.closest('[data-api-base-form]');
  if (apiForm) {
    event.preventDefault();
    const value = new FormData(apiForm).get('apiBase')?.toString().trim();
    apiBaseDraft = value || API_BASE;
    saveApiBase(apiBaseDraft);
    render();
    return;
  }

  const clientForm = event.target.closest('[data-client-form]');
  if (clientForm) {
    event.preventDefault();
    await createClientFlow({
      form: clientForm,
      backendAvailable: backendClientsAvailable,
      clientsService,
      clientsStore,
      onStart: (message) => {
        clientFormStatus = message;
        render();
      },
      onSuccess: ({ client, selectedClientId: nextSelectedClientId, message, clearDraft }) => {
        accountClients = [...accountClients, client];
        selectedClientId = nextSelectedClientId;
        saveSelectedClientId(selectedClientId);
        resetClientScopedUiState({ nextActiveView: 'clients' });
        clientsStore.saveStoredClients(accountClients);
        clientFormStatus = message;
        if (clearDraft) {
          clientDraftName = '';
          clientDraftDirectLogin = '';
          clientDraftMetricaCounter = '';
        }
        void logJournalEvent(createClientCreatedJournalEvent({
          client,
          actor: currentJournalActor(),
        }));
      },
      onError: ({ client, selectedClientId: nextSelectedClientId, message }) => {
        accountClients = [...accountClients, client];
        selectedClientId = nextSelectedClientId;
        saveSelectedClientId(selectedClientId);
        resetClientScopedUiState({ nextActiveView: 'clients' });
        clientsStore.saveStoredClients(accountClients);
        clientFormStatus = message;
        void logJournalEvent(createClientCreatedJournalEvent({
          client,
          actor: currentJournalActor(),
          metadata: { fallback: true, message },
        }));
      },
      onFinally: render,
    });
    return;
  }

  const clientSettingsForm = event.target.closest('[data-client-settings-form]');
  if (clientSettingsForm) {
    event.preventDefault();
    await saveClientSettings(clientSettingsForm);
    return;
  }

  const businessForm = event.target.closest('[data-business-context-form]');
  if (businessForm) {
    event.preventDefault();
    await saveBusinessContext(businessForm);
    return;
  }

  if (await handleAiSubmitEvent(event, {
    sendChatMessage: sendAiChatMessage,
  })) return;
});

app.addEventListener('click', async (event) => {
  if (getEditableFieldTarget(event.target)) {
    return;
  }
  const viewButton = getRouteClickTarget(event.target);
  if (viewButton) {
    event.preventDefault();
    activeView = normalizeAppView(viewButton.dataset.view || viewButton.dataset.goView);
    render();
    return;
  }
  try {
    if (await handleCabinetActionClick(event)) return;
  } catch (error) {
    console.error('DirectPilot action failed', error);
    backendClientsStatus = error?.message || 'Действие не выполнено. Проверьте подключение и повторите.';
    render();
  }
});
async function loadIntegrationStatus() {
  await loadIntegrationStatusFlow({
    integrationsService,
    onSuccess: (status) => {
      integrationStatus = status;
    },
    onError: (status) => {
      integrationStatus = status;
    },
    onFinally: render,
  });
}


async function loadClientYandexIntegration(force = false) {
  await loadClientYandexIntegrationFlow({
    selectedClientId,
    loading: clientYandexLoading,
    currentIntegration: clientYandexIntegration,
    force,
    integrationsService,
    onStart: (message) => {
      clientYandexLoading = true;
      clientYandexStatus = message;
      render();
    },
    onSuccess: ({ payload, selectedAccountId, message }) => {
      clientYandexIntegration = payload;
      clientYandexStatus = message;
      if (selectedAccountId) {
        accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, yandexAccountId: selectedAccountId } : client);
        clientsStore.saveStoredClients(accountClients);
      }
    },
    onError: (message) => {
      clientYandexStatus = message;
    },
    onFinally: () => {
      clientYandexLoading = false;
      render();
    },
  });
}


async function bindClientYandexAccount(accountId) {
  await bindClientYandexAccountFlow({
    selectedClientId,
    accountId,
    integrationsService,
    onStart: (message) => {
      clientYandexLoading = true;
      clientYandexStatus = message;
      render();
    },
    onSuccess: ({ payload, accountId: boundAccountId, message }) => {
      clientYandexIntegration = payload;
      accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, yandexAccountId: boundAccountId } : client);
      clientsStore.saveStoredClients(accountClients);
      clientYandexStatus = message;
      void autofillDirectLoginFromYandexBinding(payload);
      void logJournalEvent(createIntegrationStatusJournalEvent({
        action: 'bound',
        client: currentClient(),
        actor: currentJournalActor(),
        entityId: boundAccountId,
        metadata: { message },
      }));
    },
    onError: (message) => {
      clientYandexStatus = message;
    },
    onFinally: () => {
      clientYandexLoading = false;
      render();
    },
  });
}

async function autofillDirectLoginFromYandexBinding(integrationPayload) {
  const accountLogin = getBoundYandexAccountLogin(integrationPayload);
  const client = currentClient();
  if (!selectedClientId || !accountLogin || hasConnectedDirectLogin(client.directLogin)) return;

  const optimisticClient = { ...client, directLogin: accountLogin };
  accountClients = accountClients.map((item) => (item.id === selectedClientId ? optimisticClient : item));
  clientsStore.saveStoredClients(accountClients);
  clientSettingsStatus = 'Логин Директа подтянут из привязанного Яндекс-аккаунта.';
  render();

  if (!backendClientsAvailable) return;

  try {
    const payload = await clientsService.updateClient(selectedClientId, createClientSettingsPayload(optimisticClient, optimisticClient));
    const savedClient = clientsStore.normalizeBackendClient(payload);
    accountClients = accountClients.map((item) => (item.id === selectedClientId ? savedClient : item));
    clientsStore.saveStoredClients(accountClients);
    clientSettingsStatus = 'Логин Директа подтянут из Яндекса и сохранён в карточке клиента.';
    void logJournalEvent(createClientUpdatedJournalEvent({
      client: savedClient,
      actor: currentJournalActor(),
      metadata: { backend: true, message: clientSettingsStatus },
    }));
  } catch (error) {
    clientSettingsStatus = `${error.message || 'Не удалось сохранить логин Директа в базе.'} Логин оставлен локально, сохраните настройки клиента вручную.`;
  } finally {
    render();
  }
}


async function unbindClientYandexAccount() {
  await unbindClientYandexAccountFlow({
    selectedClientId,
    integrationsService,
    onStart: (message) => {
      clientYandexLoading = true;
      clientYandexStatus = message;
      render();
    },
    onSuccess: ({ payload, message }) => {
      clientYandexIntegration = payload;
      accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, yandexAccountId: '' } : client);
      clientsStore.saveStoredClients(accountClients);
      clientYandexStatus = message;
      void logJournalEvent(createIntegrationStatusJournalEvent({
        action: 'unbound',
        client: currentClient(),
        actor: currentJournalActor(),
        metadata: { message },
      }));
    },
    onError: (message) => {
      clientYandexStatus = message;
    },
    onFinally: () => {
      clientYandexLoading = false;
      render();
    },
  });
}

async function deleteYandexAccount(accountId) {
  if (!selectedClientId || !accountId) return;
  const confirmed = window.confirm?.('Удалить этот Яндекс-аккаунт из DirectPilot? Привязки к клиентам будут сняты, но в Яндекс.Директ ничего не изменится.');
  if (confirmed === false) return;

  clientYandexLoading = true;
  clientYandexStatus = 'Удаляем Яндекс-аккаунт из DirectPilot...';
  render();

  try {
    const payload = await integrationsService.deleteYandexAccount(selectedClientId, accountId);
    const unboundClients = new Set(payload.unbound_client_ids || payload.unboundClientIds || []);
    accountClients = accountClients.map((client) => (
      unboundClients.has(client.id) || client.yandexAccountId === accountId
        ? { ...client, yandexAccountId: '' }
        : client
    ));
    clientsStore.saveStoredClients(accountClients);
    integrationStatus = null;
    clientYandexIntegration = null;
    await loadIntegrationStatus();
    await loadClientYandexIntegration(true);
    clientYandexStatus = 'Яндекс-аккаунт удалён из DirectPilot. При необходимости подключите его заново.';
    void logJournalEvent(createIntegrationStatusJournalEvent({
      action: 'deleted',
      client: currentClient(),
      actor: currentJournalActor(),
      metadata: { accountId, message: clientYandexStatus },
    }));
  } catch (error) {
    clientYandexStatus = error.message || 'Не удалось удалить Яндекс-аккаунт.';
  } finally {
    clientYandexLoading = false;
    render();
  }
}


function setClientSettingsDraftFromForm(form) {
  clientSettingsDraft = createClientSettingsDraftFromForm(form);
  return clientSettingsDraft;
}

async function saveClientSettings(form) {
  await saveClientSettingsFlow({
    selectedClientId,
    form,
    backendAvailable: backendClientsAvailable,
    clientsService,
    clientsStore,
    currentClient: currentClient(),
    onStart: ({ draft, message }) => {
      clientSettingsDraft = draft;
      clientSettingsSaving = true;
      clientSettingsStatus = message;
      render();
    },
    onSuccess: ({ client, localUpdate, message, backend }) => {
      accountClients = accountClients.map((currentClient) => (
        currentClient.id === selectedClientId
          ? backend ? client : { ...currentClient, ...localUpdate }
          : currentClient
      ));
      clientsStore.saveStoredClients(accountClients);
      clientSettingsStatus = message;
      clientSettingsDraft = null;
      businessContext = null;
      businessContextLoadedFor = '';
      perfSummary = null;
      optimizationPlan = null;
      void logJournalEvent(createClientUpdatedJournalEvent({
        client: currentClient(),
        actor: currentJournalActor(),
        metadata: { backend: Boolean(backend), message },
      }));
    },
    onError: ({ localUpdate, message }) => {
      accountClients = accountClients.map((currentClient) => currentClient.id === selectedClientId ? { ...currentClient, ...localUpdate } : currentClient);
      clientsStore.saveStoredClients(accountClients);
      clientSettingsStatus = message;
      void logJournalEvent(createClientUpdatedJournalEvent({
        client: currentClient(),
        actor: currentJournalActor(),
        metadata: { fallback: true, message },
      }));
    },
    onFinally: () => {
      clientSettingsSaving = false;
      render();
    },
  });
}


async function deleteClient(clientId) {
  await deleteClientFlow({
    clientId,
    backendAvailable: backendClientsAvailable,
    clientsService,
    onConfirm: () => window.confirm('Удалить клиента? Это действие нельзя отменить.'),
    onStart: (message) => {
      clientSettingsStatus = message;
      render();
    },
    onSuccess: ({ clientId: deletedClientId }) => {
      accountClients = accountClients.filter((client) => client.id !== deletedClientId);
      selectedClientId = accountClients[0]?.id || '';
      saveSelectedClientId(selectedClientId);
      clientsStore.saveStoredClients(accountClients);
      clientSettingsStatus = accountClients.length ? 'Клиент удалён.' : 'Клиент удалён. Создайте нового клиента.';
      resetClientScopedUiState({ nextActiveView: 'clients' });
    },
    onError: (message) => {
      clientSettingsStatus = message;
    },
    onFinally: render,
  });
}


if (oauthReturnStatus === 'connected') {
  integrationStatus = { ...integrationStatus, message: 'Яндекс подключён. Проверяем доступные аккаунты...' };
  activeView = 'clients';
}
if (oauthReturnStatus === 'error') {
  integrationStatus = { ...integrationStatus, message: 'Яндекс не подключён. Попробуйте повторить OAuth.' };
  activeView = 'clients';
}

render();
if (page === 'app') {
  loadClientsFromApi(true);
  loadAiStatus();
  if (oauthReturnStatus) loadIntegrationStatus();
}

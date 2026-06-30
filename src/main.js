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
import {
  activeAiBudget as selectActiveAiBudget,
  activeAiModel as selectActiveAiModel,
  createAiAssistantPageContext,
  createAiChatRequestPayload,
  createAiChatStateSnapshot,
  createAiModelStateSnapshot,
  createAiPromptDebugParams,
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
  { id: 'clients', label: 'Клиенты', icon: '👥' },
  { id: 'business-context', label: 'Контекст бизнеса', icon: '🧭' },
  { id: 'integrations', label: 'Интеграции', icon: '🔌' },
  { id: 'ai', label: 'AI-аналитик', icon: '🧠' },
  { id: 'optimization', label: 'Оптимизация', icon: '🎯' },
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
let perfSummary = null;
let perfLoading = false;
let perfStatus = '';
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
const CUSTOM_MODEL_VALUE = aiStore.CUSTOM_MODEL_VALUE;
const aiFeatureState = createAiFeatureState();
let pendingEditableFocusTarget = null;

function storageKey(key) {
  return scopedStorageKey(key);
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
      if (shouldResetBusinessContext) businessContext = null;
    },
    onFallback: ({ clients, selectedClientId: fallbackSelectedClientId, message }) => {
      if (!backendClientsLoaded && clients.length) {
        accountClients = clients;
        selectedClientId = fallbackSelectedClientId || '';
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

function formatNumberSafe(value) {
  return typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('ru-RU').format(value) : '0';
}

function formatMoney(value) {
  return `${formatNumberSafe(value)} ₽`;
}

function formatPercent(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '0%';
  return `${value.toFixed(1).replace('.', ',')}%`;
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
  return `
    <div class="appShell">
      <aside class="sidebar">
        <div class="brand"><span class="logo">D</span><span>DirectPilot AI</span></div>
        <div class="clientMini">
          <span>${showClientSelector ? 'Активный клиент' : 'Аккаунт'}</span>
          <strong>${escapeHtml(showClientSelector ? currentClientName() : currentEmail || 'Гость')}</strong>
          ${showClientSelector ? `<small>${escapeHtml(client.directLogin || 'Direct не подключен')}</small>` : ''}
        </div>
        <nav>${navItems.map((item) => `<button class="${activeView === item.id ? 'active' : ''}" data-view="${item.id}"><span>${item.icon}</span>${item.label}</button>`).join('')}</nav>
        <button class="logoutButton" data-logout>Выйти</button>
      </aside>
      <main class="dashboard">
        <header class="dashboardHeader">
          <div>
            <span class="eyebrow">Кабинет</span>
            <h1>${escapeHtml(activeView === 'dashboard' ? 'Обзор проекта' : navItems.find((item) => item.id === activeView)?.label || 'DirectPilot')}</h1>
          </div>
          <div class="headerActions">
            ${showClientSelector ? renderClientSelector() : ''}
            <button class="secondaryButton" data-open-settings>API</button>
          </div>
        </header>
        ${renderSettingsPanel()}
        ${content}
      </main>
    </div>
  `;
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
  const hasYandexBinding = Boolean(client.yandexAccountId || clientYandexIntegration?.selected_account?.id || clientYandexIntegration?.yandex_account_id);
  const hasSync = syncJobs.some((job) => job.status === 'completed') || hasPerformanceData();
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
    yandex: ['Привяжите аккаунт Яндекса', 'integrations'],
    metrica: ['Заполните цели и счётчик', 'clients'],
    context: ['Заполните контекст бизнеса', 'business-context'],
    sync: ['Запустите синхронизацию', 'dashboard'],
    optimization: ['Сформируйте черновики оптимизации', 'optimization'],
  };
  const [nextAction, targetView] = actions[blocking.id] || ['Проверьте настройки', 'dashboard'];
  return { ...blocking, nextAction, targetView };
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
  return createAiPromptDebugParams(currentAiModelState(), aiFeatureState.chat.selectedCampaignName);
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
      preset: aiFeatureState.model.selectedPreset,
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
  await sendAiChatMessageFlow({
    message: message || aiFeatureState.chat.input,
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
      render();
    },
    onSuccess: ({ messages, toolTraces }) => {
      aiFeatureState.chat.messages = messages;
      aiFeatureState.chat.toolTraces = toolTraces;
    },
    onError: ({ message: errorMessage, payload, messages }) => {
      aiFeatureState.chat.error = errorMessage;
      aiFeatureState.chat.errorDetails = payload;
      if (messages) {
        aiFeatureState.chat.messages = messages;
      }
    },
    onFinally: () => {
      aiFeatureState.chat.loading = false;
      render();
    },
  });
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


async function loadBusinessContext() {
  if (!selectedClientId || businessContextLoading) return;
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
    const payload = await syncService.runClientSync(selectedClientId);
    syncStatusMessage = `Синхронизация запущена. Статус: ${syncJobStatusLabel(payload.status)}.`;
    await loadSyncJobs();
    await loadPerformanceSummary();
  } catch (error) {
    syncStatusMessage = error.message || 'Не удалось запустить синхронизацию.';
  } finally {
    syncLoading = false;
    render();
  }
}


async function loadSyncJobs() {
  if (!selectedClientId || syncJobsLoading) return;
  syncJobsLoading = true;
  render();
  try {
    syncJobs = await syncService.fetchSyncJobs(selectedClientId);
  } catch (error) {
    if (!syncStatusMessage) syncStatusMessage = error.message || 'История синхронизаций недоступна.';
  } finally {
    syncJobsLoading = false;
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
        <article><span>Последний статус</span><strong>${syncJobs[0] ? syncJobStatusLabel(syncJobs[0].status) : 'Нет запусков'}</strong></article>
        <article><span>Backend</span><strong>${backendClientsAvailable ? 'Доступен' : 'Fallback'}</strong></article>
      </div>
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
      <div class="syncJobs">
        ${syncJobsLoading ? '<p>Загружаем историю...</p>' : syncJobs.length ? syncJobs.slice(0, 5).map((job) => `
          <article>
            <div><strong>${syncJobStatusLabel(job.status)}</strong><span>${escapeHtml(job.message || 'Без сообщения')}</span></div>
            <small>${normalizeDate(job.created_at)}</small>
          </article>
        `).join('') : '<p>Истории синхронизаций пока нет.</p>'}
      </div>
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
  if (!clientYandexIntegration?.selected_account && !client.yandexAccountId) issues.push(['Привязка Яндекса', 'Выберите аккаунт из OAuth-доступов во вкладке Интеграции.']);
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

function renderYesterdaySummaryPanel() {
  const campaignsCount = perfSummary?.campaigns?.length || 0;
  const totalSpend = perfSummary?.totalSpend || 0;
  const totalConversions = perfSummary?.totalConversions || 0;
  const candidateNegatives = perfSummary?.searchQueryInsights?.candidateNegativeKeywords || 0;
  return `
    <section class="panel summaryPanel">
      <div class="panelHeader">
        <div>
          <h3>Сводка за вчера</h3>
          <p>Быстрый статус по данным после последней синхронизации.</p>
        </div>
        <button class="secondaryButton" data-load-performance ${selectedClientId && !perfLoading ? '' : 'disabled'}>${perfLoading ? 'Загрузка...' : 'Обновить сводку'}</button>
      </div>
      ${perfStatus ? `<div class="authStatus integrationStatus">${escapeHtml(perfStatus)}</div>` : ''}
      <div class="kpiGrid">
        <article class="kpi"><span>Кампаний</span><strong>${formatNumberSafe(campaignsCount)}</strong></article>
        <article class="kpi"><span>Расход</span><strong>${formatMoney(totalSpend)}</strong></article>
        <article class="kpi"><span>Конверсий</span><strong>${formatNumberSafe(totalConversions)}</strong></article>
        <article class="kpi"><span>Минус-слова</span><strong>${formatNumberSafe(candidateNegatives)}</strong></article>
      </div>
      ${!hasPerformanceData() ? '<div class="authStatus integrationStatus">Данных пока нет. Запустите синхронизацию или проверьте настройки клиента.</div>' : ''}
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
  const campaignsData = perfSummary?.campaigns || [];
  const insights = perfSummary?.searchQueryInsights;
  return `
    <section class="panel performancePanel">
      <div class="panelHeader">
        <div>
          <h3>Performance summary</h3>
          <p>Кампании, CPA и поисковые запросы, которые AI использует для рекомендаций.</p>
        </div>
        <button class="secondaryButton" data-load-performance ${selectedClientId && !perfLoading ? '' : 'disabled'}>${perfLoading ? 'Загрузка...' : 'Обновить'}</button>
      </div>
      ${campaignsData.length ? `
        <div class="dataTableWrap">
          <table class="dataTable">
            <thead><tr><th>Кампания</th><th>Расход</th><th>Конверсии</th><th>CPA</th></tr></thead>
            <tbody>${campaignsData.slice(0, 8).map((campaign) => `<tr><td>${escapeHtml(campaign.name)}</td><td>${formatMoney(campaign.cost || 0)}</td><td>${formatNumberSafe(campaign.conversions || 0)}</td><td>${formatMoney(campaign.cpa || 0)}</td></tr>`).join('')}</tbody>
          </table>
        </div>
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

  return renderShell(contentRenderer({
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
  }));
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
  const contentRenderer = resolvePageContentRenderer('integrations');

  if (typeof contentRenderer !== 'function') {
    return renderShell(`
      <div class="pageIntro"><span class="eyebrow">Интеграции</span><h2>Интеграции временно недоступны</h2><p>Модуль интеграций не зарегистрирован. Проверьте src/pages/index.js.</p></div>
    `);
  }

  return renderShell(contentRenderer(integrationsPageContext()));
}

function aiAssistantPageContext() {
  return createAiAssistantPageContext({
    selectedClientId,
    selectedClient: currentClient(),
    aiStatus: aiFeatureState.model.status,
    selectedAiModel: aiFeatureState.model.selectedModel,
    customAiModel: aiFeatureState.model.customModel,
    customModelValue: CUSTOM_MODEL_VALUE,
    selectedAiPreset: aiFeatureState.model.selectedPreset,
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

function render() {
  activeView = normalizeAppView(activeView);
  const views = {
    landing: renderLanding,
    login: renderLogin,
    dashboard: renderDashboardViaPageModule,
    clients: renderClients,
    'business-context': renderBusinessContext,
    audit: renderAudit,
    recommendations: renderRecommendations,
    ai: renderAiAssistant,
    reports: renderReports,
    autopilot: renderAutopilot,
    integrations: renderIntegrations,
    optimization: renderOptimization,
  };
  const renderView = views[activeView] || renderDashboard;
  app.innerHTML = renderView();
  document.body.dataset.view = activeView;
  if (activeView === 'login') {
    const emailInput = app.querySelector('input[name="email"]');
    if (emailInput) emailInput.value = authEmail;
  }
  if (activeView === 'integrations' && !integrationStatus.message && integrationStatus.connected === undefined) {
    loadIntegrationStatus();
  }
  if (activeView === 'integrations' && selectedClientId) {
    loadClientYandexIntegration();
  }
  if (activeView === 'dashboard' && selectedClientId) {
    if (!syncJobs.length && !syncJobsLoading) loadSyncJobs();
    if (!perfSummary && !perfLoading) loadPerformanceSummary();
    if (!clientYandexIntegration && !clientYandexLoading) loadClientYandexIntegration();
    if (!businessContext && !businessContextLoading) loadBusinessContext();
  }
  if (activeView === 'business-context' && selectedClientId && !businessContextLoading) {
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
  if (activeView === 'ai' && aiFeatureState.model.status.message === 'Статус OpenRouter ещё не загружен.') {
    loadAiStatus();
  }
  if (activeView === 'ai' && selectedClientId && !businessContextLoading) {
    loadBusinessContext();
  }
  if (activeView !== 'landing' && activeView !== 'login') {
    loadClientsFromApi();
  }
}

['pointerdown', 'mousedown', 'mouseup', 'click'].forEach((eventName) => {
  app.addEventListener(eventName, (event) => {
    if (isPlainTextInputTarget(event.target) && !isInteractiveActionTarget(event.target)) {
      event.stopPropagation();
    }
  }, true);
});

['pointerdown', 'mousedown'].forEach((eventName) => {
  app.addEventListener(eventName, (event) => {
    if (isInteractiveActionTarget(event.target)) return;
    pendingEditableFocusTarget = getEditableFieldTarget(event.target);
  }, true);
});

app.addEventListener('focusin', (event) => {
  const target = getEditableFieldTarget(event.target);
  if (target) pendingEditableFocusTarget = target;
});

app.addEventListener('input', (event) => {
  const target = getEditableFieldTarget(event.target);
  if (target) pendingEditableFocusTarget = target;
  const authInput = event.target.closest('input[name="email"], input[name="code"]');
  if (authInput?.name === 'email') authEmail = authInput.value;
  if (authInput?.name === 'code') authCode = authInput.value;
  handleAiInputEvent(event, {
    setCustomModel: (value) => {
      aiFeatureState.model.customModel = value;
    },
    setSearchQueryLimit: (value) => {
      aiFeatureState.model.searchQueryLimit = value;
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
});

app.addEventListener('change', (event) => {
  if (handleAiChangeEvent(event, {
    customModelValue: CUSTOM_MODEL_VALUE,
    setModel: (value, customValue) => {
      aiFeatureState.model.selectedModel = value;
      if (customValue !== undefined) aiFeatureState.model.customModel = customValue;
    },
    setPreset: (value) => {
      aiFeatureState.model.selectedPreset = value;
    },
    setMaxTokensMode: (value) => {
      aiFeatureState.model.maxTokensMode = value;
    },
    setToolResultsMode: (value) => {
      aiFeatureState.model.toolResultsMode = value;
    },
    setChatHistoryLimit: (value) => {
      aiFeatureState.model.chatHistoryLimit = value;
    },
    setCompactContext: (value) => {
      aiFeatureState.model.compactContext = value;
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
  return target?.closest?.('input, textarea, select, [contenteditable="true"]');
}

function isPlainTextInputTarget(target) {
  const field = getEditableFieldTarget(target);
  if (!field) return false;
  return !field.closest('[data-client-menu], .clientMenu, .heroActions, .headerActions');
}

function isInteractiveActionTarget(target) {
  return Boolean(target?.closest?.('button, a, label, select, option, [data-client-menu], .clientMenu, .heroActions, .headerActions'));
}

function restorePendingEditableFocus() {
  if (!pendingEditableFocusTarget || !document.body.contains(pendingEditableFocusTarget)) return;
  if (document.activeElement === pendingEditableFocusTarget) return;
  pendingEditableFocusTarget.focus({ preventScroll: true });
}

app.addEventListener('submit', async (event) => {
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
        clientsStore.saveStoredClients(accountClients);
        clientFormStatus = message;
        if (clearDraft) {
          clientDraftName = '';
          clientDraftDirectLogin = '';
          clientDraftMetricaCounter = '';
        }
      },
      onError: ({ client, selectedClientId: nextSelectedClientId, message }) => {
        accountClients = [...accountClients, client];
        selectedClientId = nextSelectedClientId;
        saveSelectedClientId(selectedClientId);
        clientsStore.saveStoredClients(accountClients);
        clientFormStatus = message;
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
  const viewButton = event.target.closest('[data-view]');
  if (viewButton) {
    activeView = normalizeAppView(viewButton.dataset.view);
    render();
    return;
  }
  const goViewButton = event.target.closest('[data-go-view]');
  if (goViewButton) {
    activeView = normalizeAppView(goViewButton.dataset.goView);
    render();
    return;
  }
  if (event.target.closest('[data-logout]')) {
    clearSession();
    window.location.href = 'login.html';
    return;
  }
  if (event.target.closest('[data-auth-back]')) {
    authStep = 'email';
    authStatus = '';
    authCode = '';
    render();
    return;
  }
  if (event.target.closest('[data-open-settings]')) {
    const panel = app.querySelector('[data-settings-panel]');
    if (panel) panel.hidden = !panel.hidden;
    return;
  }
  if (event.target.closest('[data-client-menu-toggle]')) {
    const menu = app.querySelector('[data-client-menu]');
    if (menu) menu.hidden = !menu.hidden;
    return;
  }
  const clientButton = event.target.closest('[data-client-id], [data-select-client]');
  if (clientButton) {
    selectedClientId = clientButton.dataset.clientId || clientButton.dataset.selectClient;
    saveSelectedClientId(selectedClientId);
    businessContext = null;
    businessContextDraft = null;
    clientYandexIntegration = null;
    syncJobs = [];
    perfSummary = null;
    optimizationPlan = null;
    optimizationActions = [];
    optimizationActionsLoadedFor = '';
    resetAiClientScopedState(aiFeatureState);
    activeView = 'dashboard';
    render();
    return;
  }
  if (event.target.closest('[data-sync-client]')) {
    await startSync();
    return;
  }
  if (event.target.closest('[data-load-performance]')) {
    await loadPerformanceSummary();
    return;
  }
  if (event.target.closest('[data-load-optimization-plan]')) {
    await loadOptimizationPlan();
    return;
  }
  if (event.target.closest('[data-load-optimization-actions]')) {
    await loadOptimizationActions(true);
    return;
  }
  if (event.target.closest('[data-create-optimization-drafts]')) {
    await createOptimizationDraftsFromPlan();
    return;
  }
  const updateActionButton = event.target.closest('[data-update-optimization-action]');
  if (updateActionButton) {
    await updateOptimizationActionStatus(updateActionButton.dataset.updateOptimizationAction, updateActionButton.dataset.status);
    return;
  }
  const previewActionButton = event.target.closest('[data-preview-optimization-action]');
  if (previewActionButton) {
    await loadOptimizationExecutionPreview(previewActionButton.dataset.previewOptimizationAction);
    return;
  }
  if (event.target.closest('[data-refresh-client-yandex]')) {
    await loadClientYandexIntegration(true);
    return;
  }
  const bindYandexButton = event.target.closest('[data-bind-yandex-account]');
  if (bindYandexButton) {
    await bindClientYandexAccount(bindYandexButton.dataset.bindYandexAccount);
    return;
  }
  if (event.target.closest('[data-unbind-yandex]')) {
    await unbindClientYandexAccount();
    return;
  }
  if (event.target.closest('[data-reset-business-context]')) {
    businessContextDraft = businessContext || defaultBusinessContext();
    render();
    return;
  }
  const copyButton = event.target.closest('[data-copy-text]');
  if (copyButton) {
    await navigator.clipboard?.writeText(copyButton.dataset.copyText || '');
    return;
  }
  if (event.target.closest('[data-reset-client-settings]')) {
    clientSettingsDraft = null;
    render();
    return;
  }
  const deleteButton = event.target.closest('[data-delete-client]');
  if (deleteButton) {
    await deleteClient(deleteButton.dataset.deleteClient);
    return;
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
  })) return;
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
      perfSummary = null;
      optimizationPlan = null;
    },
    onError: ({ localUpdate, message }) => {
      accountClients = accountClients.map((currentClient) => currentClient.id === selectedClientId ? { ...currentClient, ...localUpdate } : currentClient);
      clientsStore.saveStoredClients(accountClients);
      clientSettingsStatus = message;
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
      if (selectedClientId) saveSelectedClientId(selectedClientId);
      clientsStore.saveStoredClients(accountClients);
      clientSettingsStatus = accountClients.length ? 'Клиент удалён.' : 'Клиент удалён. Создайте нового клиента.';
      activeView = 'clients';
    },
    onError: (message) => {
      clientSettingsStatus = message;
    },
    onFinally: render,
  });
}


if (oauthReturnStatus === 'connected') {
  integrationStatus = { ...integrationStatus, message: 'Яндекс подключён. Проверяем доступные аккаунты...' };
  activeView = 'integrations';
}
if (oauthReturnStatus === 'error') {
  integrationStatus = { ...integrationStatus, message: 'Яндекс не подключён. Попробуйте повторить OAuth.' };
  activeView = 'integrations';
}

render();
if (page === 'app') {
  loadClientsFromApi(true);
  loadAiStatus();
  if (oauthReturnStatus) loadIntegrationStatus();
}

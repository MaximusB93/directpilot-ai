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
import * as aiService from './services/ai-service.js';
import * as businessContextService from './services/business-context-service.js';
import * as clientsService from './services/clients-service.js';
import * as integrationsService from './services/integrations-service.js';
import * as optimizationService from './services/optimization-service.js';
import * as performanceService from './services/performance-service.js';
import * as syncService from './services/sync-service.js';
import * as aiStore from './stores/ai-store.js';
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
const primaryAppViews = new Set(navItems.map((item) => item.id));
const legacyViewRedirects = {
  audit: 'ai',
  recommendations: 'ai',
  reports: 'dashboard',
  autopilot: 'optimization',
  context: 'business-context',
  memory: 'business-context',
  'ai-models': 'ai',
  models: 'ai',
};

function normalizeAppView(view) {
  if (page !== 'app') return view;
  if (primaryAppViews.has(view)) return view;
  return legacyViewRedirects[view] || 'dashboard';
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
const initialAiModelState = aiStore.createInitialAiModelState();
const initialAiChatState = aiStore.createInitialAiChatState();
const initialAiGenerationState = aiStore.createInitialAiGenerationState();

let aiStatus = initialAiModelState.status;
let selectedAiModel = initialAiModelState.model;
let customAiModel = initialAiModelState.customModel;
let selectedAiPreset = initialAiModelState.preset;
let aiMaxTokensMode = initialAiModelState.maxTokensMode;
let aiCompactContext = initialAiModelState.compactContext;
let aiToolResultsMode = initialAiModelState.toolResultsMode;
let aiChatHistoryLimit = initialAiModelState.chatHistoryLimit;
let aiSearchQueryLimit = initialAiModelState.searchQueryLimit;
let aiLoading = initialAiGenerationState.loading;
let aiResult = initialAiGenerationState.result;
let aiError = initialAiGenerationState.error;
let aiPromptDebug = initialAiGenerationState.promptDebug;
let aiPromptDebugLoading = initialAiGenerationState.promptDebugLoading;
let aiPromptDebugError = initialAiGenerationState.promptDebugError;
let aiRecommendationsLoading = initialAiGenerationState.recommendationsLoading;
let aiRecommendationsError = initialAiGenerationState.recommendationsError;
let clientAiRecommendations = initialAiGenerationState.clientRecommendations;
let aiMemoryStatus = initialAiGenerationState.memoryStatus;
let aiChatMessages = initialAiChatState.messages.map((message) => ({ ...message }));
let aiChatInput = initialAiChatState.input;
let aiChatLoading = initialAiChatState.loading;
let aiChatError = initialAiChatState.error;
let aiChatErrorDetails = initialAiChatState.errorDetails;
let aiChatToolTraces = initialAiChatState.toolTraces;
let aiChatSelectedCampaignName = initialAiChatState.selectedCampaignName;
let pendingEditableFocusTarget = null;

function storageKey(key) {
  return scopedStorageKey(key);
}

const clientsStore = clientStore.createClientStore(storageKey);

function loadSelectedClientId() {
  return clientStore.loadSelectedClientId(storageKey, accountClients[0]?.id || '');
}

function saveSelectedClientId(clientId) {
  clientStore.saveSelectedClientId(storageKey, clientId);
}

async function loadClientsFromApi(force = false) {
  if (page !== 'app') return;
  if (backendClientsLoading || (backendClientsLoaded && !force)) return;
  backendClientsLoading = true;
  try {
    const payload = await clientsService.fetchClients();
    accountClients = payload.map(clientsStore.normalizeBackendClient);
    backendClientsLoaded = true;
    backendClientsAvailable = true;
    backendClientsStatus = accountClients.length ? 'Клиенты загружены из базы данных.' : 'В базе пока нет клиентов. Создайте первого клиента.';
    const storedSelected = loadSelectedClientId();
    selectedClientId = accountClients.find((client) => client.id === storedSelected)?.id || accountClients[0]?.id || '';
    if (selectedClientId) saveSelectedClientId(selectedClientId);
    clientsStore.saveStoredClients(accountClients);
    if (!businessContextLoading) businessContext = null;
  } catch (error) {
    if (!backendClientsLoaded) {
      const storedClients = clientsStore.loadStoredClients();
      if (storedClients.length) {
        accountClients = storedClients;
        selectedClientId = accountClients.find((client) => client.id === loadSelectedClientId())?.id || accountClients[0]?.id || '';
      }
    }
    backendClientsAvailable = false;
    backendClientsStatus = 'Backend недоступен, временно используем локальное хранилище.';
  } finally {
    backendClientsLoading = false;
    render();
  }
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
  return {
    companyName: payload?.company_name || '',
    websiteUrl: payload?.website_url || '',
    industry: payload?.industry || '',
    productDescription: payload?.product_description || '',
    targetAudience: payload?.target_audience || '',
    geography: payload?.geography || '',
    mainOffers: payload?.main_offers || '',
    conversionActions: payload?.conversion_actions || '',
    averageOrderValue: payload?.average_order_value || '',
    leadValueNotes: payload?.lead_value_notes || '',
    businessConstraints: payload?.business_constraints || '',
    negativeTopics: payload?.negative_topics || '',
    landingPageNotes: payload?.landing_page_notes || '',
    competitorNotes: payload?.competitor_notes || '',
    manualNotes: payload?.manual_notes || '',
    memoryNotes: payload?.memory_notes || '',
    sourceNotes: payload?.source_notes || '',
    updatedAt: payload?.updated_at || '',
  };
}

function businessContextPayload(context) {
  return {
    company_name: context.companyName || '',
    website_url: context.websiteUrl || '',
    industry: context.industry || '',
    product_description: context.productDescription || '',
    target_audience: context.targetAudience || '',
    geography: context.geography || '',
    main_offers: context.mainOffers || '',
    conversion_actions: context.conversionActions || '',
    average_order_value: context.averageOrderValue || '',
    lead_value_notes: context.leadValueNotes || '',
    business_constraints: context.businessConstraints || '',
    negative_topics: context.negativeTopics || '',
    landing_page_notes: context.landingPageNotes || '',
    competitor_notes: context.competitorNotes || '',
    manual_notes: context.manualNotes || '',
    memory_notes: context.memoryNotes || '',
    source_notes: context.sourceNotes || '',
  };
}

function defaultBusinessContext() {
  const client = currentClient();
  return normalizeBusinessContext({
    company_name: client.name || '',
    website_url: '',
    industry: client.segment || '',
  });
}

function hasBusinessContextData(context) {
  if (!context) return false;
  const fields = ['industry', 'productDescription', 'targetAudience', 'geography', 'mainOffers', 'conversionActions', 'businessConstraints'];
  return fields.some((field) => String(context[field] || '').trim().length > 0);
}

function businessContextCopyText(context = businessContext || businessContextDraft || defaultBusinessContext()) {
  const rows = [
    ['Компания', context.companyName],
    ['Сайт', context.websiteUrl],
    ['Ниша', context.industry],
    ['Продукт', context.productDescription],
    ['ЦА', context.targetAudience],
    ['География', context.geography],
    ['Офферы', context.mainOffers],
    ['Целевые действия', context.conversionActions],
    ['Средний чек / ценность лида', context.averageOrderValue],
    ['Качественные лиды', context.leadValueNotes],
    ['Ограничения бизнеса', context.businessConstraints],
    ['Нерелевантные темы', context.negativeTopics],
    ['Посадочные страницы', context.landingPageNotes],
    ['Конкуренты', context.competitorNotes],
    ['Заметки специалиста', context.manualNotes],
    ['Память проекта', context.memoryNotes],
    ['Источники', context.sourceNotes],
  ];
  return rows.map(([label, value]) => `${label}: ${value || '—'}`).join('\n');
}

function setBusinessContextDraftFromForm(form) {
  const formData = new FormData(form);
  businessContextDraft = normalizeBusinessContext({
    company_name: formData.get('companyName'),
    website_url: formData.get('websiteUrl'),
    industry: formData.get('industry'),
    product_description: formData.get('productDescription'),
    target_audience: formData.get('targetAudience'),
    geography: formData.get('geography'),
    main_offers: formData.get('mainOffers'),
    conversion_actions: formData.get('conversionActions'),
    average_order_value: formData.get('averageOrderValue'),
    lead_value_notes: formData.get('leadValueNotes'),
    business_constraints: formData.get('businessConstraints'),
    negative_topics: formData.get('negativeTopics'),
    landing_page_notes: formData.get('landingPageNotes'),
    competitor_notes: formData.get('competitorNotes'),
    manual_notes: formData.get('manualNotes'),
    memory_notes: formData.get('memoryNotes'),
    source_notes: formData.get('sourceNotes'),
  });
  return businessContextDraft;
}

function businessContextForAi() {
  const context = businessContext || businessContextDraft;
  if (!hasBusinessContextData(context)) return null;
  return businessContextPayload(context);
}

function contextCompletenessScore(context = businessContext || businessContextDraft) {
  if (!context) return 0;
  const important = ['industry', 'productDescription', 'targetAudience', 'geography', 'mainOffers', 'conversionActions', 'businessConstraints', 'negativeTopics'];
  const filled = important.filter((field) => String(context[field] || '').trim().length > 0).length;
  return Math.round((filled / important.length) * 100);
}

function campaignOptions() {
  return (perfSummary?.campaigns || []).map((campaign) => campaign.name).filter(Boolean);
}

function currentAiModelState() {
  return {
    status: aiStatus,
    model: selectedAiModel,
    customModel: customAiModel,
    preset: selectedAiPreset,
    maxTokensMode: aiMaxTokensMode,
    compactContext: aiCompactContext,
    toolResultsMode: aiToolResultsMode,
    chatHistoryLimit: aiChatHistoryLimit,
    searchQueryLimit: aiSearchQueryLimit,
  };
}

function currentAiChatState() {
  return {
    messages: aiChatMessages,
    input: aiChatInput,
    loading: aiChatLoading,
    error: aiChatError,
    errorDetails: aiChatErrorDetails,
    toolTraces: aiChatToolTraces,
    selectedCampaignName: aiChatSelectedCampaignName,
  };
}

function activeAiModel() {
  return aiStore.activeAiModel(currentAiModelState());
}

function activeAiBudget() {
  return aiStore.activeAiBudget(currentAiModelState());
}

function aiChatRequestPayload(message) {
  return aiStore.createAiChatRequestPayload({
    clientId: selectedClientId,
    message,
    modelState: currentAiModelState(),
    chatState: currentAiChatState(),
    businessContext: businessContextForAi(),
  });
}

function aiPromptDebugParams() {
  return aiStore.createAiPromptDebugParams(currentAiModelState(), aiChatSelectedCampaignName);
}


async function loadAiPromptDebug() {
  if (!selectedClientId) {
    aiPromptDebugError = 'Сначала выберите клиента.';
    render();
    return;
  }
  aiPromptDebugLoading = true;
  aiPromptDebugError = '';
  render();
  try {
    aiPromptDebug = await aiService.fetchAiPromptDebug(selectedClientId, aiPromptDebugParams());
  } catch (error) {
    aiPromptDebugError = error.message || 'Не удалось проверить размер AI-контекста';
  } finally {
    aiPromptDebugLoading = false;
    render();
  }
}


async function requestAiRecommendations() {
  if (!selectedClientId) {
    aiRecommendationsError = 'Сначала выберите клиента.';
    render();
    return;
  }
  aiRecommendationsLoading = true;
  aiRecommendationsError = '';
  render();
  try {
    const budget = activeAiBudget();
    const payload = await aiService.fetchClientAiRecommendations(selectedClientId, {
      model: activeAiModel(),
      preset: selectedAiPreset,
      max_tokens: budget.maxTokens,
      target_context_tokens: budget.targetContextTokens,
      include_business_context: true,
      business_context: businessContextForAi(),
      compact_context: aiCompactContext,
      include_raw_tool_results: aiToolResultsMode === 'raw' || budget.includeRawToolResults,
      search_query_limit: Number(aiSearchQueryLimit) || 20,
    });
    clientAiRecommendations = payload;
    if (payload.business_context_memory_note) {
      await saveAiMemoryNote(payload.business_context_memory_note);
    }
  } catch (error) {
    aiRecommendationsError = error.message || 'Не удалось сформировать AI-рекомендации';
  } finally {
    aiRecommendationsLoading = false;
    render();
  }
}


async function sendAiChatMessage(message) {
  const text = String(message || aiChatInput || '').trim();
  if (!text || aiChatLoading) return;
  aiChatMessages = aiStore.addAiChatMessage(currentAiChatState(), { role: 'user', content: text }).messages;
  aiChatInput = '';
  aiChatLoading = true;
  aiChatError = '';
  aiChatErrorDetails = null;
  render();
  try {
    const payload = await aiService.requestAiChat(aiChatRequestPayload(text));
    aiChatMessages = aiStore.addAiChatMessage(currentAiChatState(), { role: 'assistant', content: payload.answer || 'Нет ответа.' }).messages;
    aiChatToolTraces = payload.tool_traces || [];
    if (payload.business_context_memory_note) {
      await saveAiMemoryNote(payload.business_context_memory_note);
    }
  } catch (error) {
    const payload = error.payload || {};
    aiChatError = error.message || 'AI-чат не вернул ответ';
    aiChatErrorDetails = payload;
    if (payload.retry_suggestion) {
      aiChatMessages = aiStore.addAiChatMessage(currentAiChatState(), { role: 'assistant', content: `Не смог собрать ответ: ${payload.retry_suggestion}` }).messages;
    }
  } finally {
    aiChatLoading = false;
    render();
  }
}


async function saveAiMemoryNote(note) {
  if (!selectedClientId || !note) return;
  aiMemoryStatus = 'Сохраняем вывод в память проекта...';
  try {
    const payload = await businessContextService.saveBusinessContextMemoryNote(selectedClientId, note);
    businessContext = normalizeBusinessContext(payload);
    businessContextDraft = businessContext;
    aiMemoryStatus = 'AI-вывод сохранён в память проекта.';
  } catch (error) {
    aiMemoryStatus = error.message || 'Не удалось сохранить вывод в память проекта.';
  }
}


async function loadAiStatus() {
  try {
    aiStatus = aiStore.normalizeAiStatus(await aiService.fetchOpenRouterStatus());
  } catch (error) {
    aiStatus = aiStore.normalizeAiStatus({
      configured: false,
      models: [],
      message: 'Backend недоступен, OpenRouter не проверен.',
    });
  }
  render();
}


async function generateAiInsight(prompt) {
  aiLoading = true;
  aiError = '';
  aiResult = null;
  render();
  try {
    const budget = activeAiBudget();
    aiResult = await aiService.generateAiInsight({
      prompt,
      model: activeAiModel(),
      max_tokens: budget.maxTokens,
      preset: selectedAiPreset,
      business_context: businessContextForAi(),
    });
  } catch (error) {
    aiError = error.message || 'Не удалось получить AI-ответ';
  } finally {
    aiLoading = false;
    render();
  }
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
  if (!payload) return null;
  return {
    ...payload,
    dailyBudgetRecommendations: Array.isArray(payload.daily_budget_recommendations) ? payload.daily_budget_recommendations : payload.dailyBudgetRecommendations || [],
    deviceAdjustments: Array.isArray(payload.device_adjustments) ? payload.device_adjustments : payload.deviceAdjustments || [],
    generatedAt: payload.generated_at || payload.generatedAt || '',
  };
}

function normalizeOptimizationAction(action) {
  return {
    ...action,
    actionType: action.action_type || action.actionType,
    entityType: action.entity_type || action.entityType,
    entityId: action.entity_id || action.entityId,
    entityName: action.entity_name || action.entityName,
    currentValue: action.current_value ?? action.currentValue,
    proposedValue: action.proposed_value ?? action.proposedValue,
    createdAt: action.created_at || action.createdAt,
    updatedAt: action.updated_at || action.updatedAt,
  };
}

function normalizeOptimizationPreview(payload) {
  return {
    ...payload,
    actionId: payload.action_id || payload.actionId,
    steps: Array.isArray(payload.steps) ? payload.steps : [],
    warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
    directPayload: payload.direct_payload || payload.directPayload || null,
    canApply: Boolean(payload.can_apply ?? payload.canApply),
  };
}

function getFilteredOptimizationActions() {
  return optimizationActions.filter((action) => optimizationActionFilter === 'all' || action.status === optimizationActionFilter);
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
  if (!selectedClientId || optimizationPlanLoading) return;
  optimizationPlanLoading = true;
  optimizationStatus = 'Формируем план оптимизации...';
  render();
  try {
    const payload = await optimizationService.fetchOptimizationPlan(selectedClientId);
    optimizationPlan = normalizeOptimizationPlan(payload);
    optimizationStatus = 'План оптимизации обновлён.';
  } catch (error) {
    optimizationStatus = error.message || 'Не удалось сформировать план оптимизации.';
  } finally {
    optimizationPlanLoading = false;
    render();
  }
}


async function loadOptimizationActions(force = false) {
  if (!selectedClientId || optimizationActionsLoading) return;
  if (!force && optimizationActionsLoadedFor === selectedClientId) return;
  optimizationActionsLoading = true;
  optimizationActionsStatus = 'Загружаем черновики согласования...';
  render();
  try {
    const payload = await optimizationService.fetchOptimizationActions(selectedClientId, optimizationActionFilter);
    optimizationActions = Array.isArray(payload) ? payload.map(normalizeOptimizationAction) : [];
    optimizationActionsLoadedFor = selectedClientId;
    optimizationActionsStatus = optimizationActions.length ? 'Черновики согласования загружены.' : 'Черновиков пока нет. Сохраните план оптимизации как черновики.';
  } catch (error) {
    optimizationActionsStatus = error.message || 'Не удалось загрузить черновики согласования.';
  } finally {
    optimizationActionsLoading = false;
    render();
  }
}

async function createOptimizationDraftsFromPlan() {
  if (!selectedClientId || optimizationActionsLoading) return;
  optimizationActionsLoading = true;
  optimizationActionsStatus = 'Сохраняем рекомендации как черновики...';
  render();
  try {
    const payload = await optimizationService.saveOptimizationPlanAsDrafts(selectedClientId);
    optimizationActions = Array.isArray(payload) ? payload.map(normalizeOptimizationAction) : [];
    optimizationActionsLoadedFor = selectedClientId;
    optimizationActionsStatus = `Сохранено черновиков: ${optimizationActions.length}.`;
  } catch (error) {
    optimizationActionsStatus = error.message || 'Не удалось сохранить черновики.';
  } finally {
    optimizationActionsLoading = false;
    render();
  }
}


async function updateOptimizationActionStatus(actionId, status, reviewerNote = '') {
  if (!selectedClientId || !actionId) return;
  optimizationActionsStatus = 'Обновляем статус черновика...';
  render();
  try {
    const payload = await optimizationService.updateOptimizationAction(selectedClientId, actionId, {
      status,
      reviewer_note: reviewerNote,
    });
    const updated = normalizeOptimizationAction(payload);
    optimizationActions = optimizationActions.map((action) => action.id === actionId ? updated : action);
    optimizationActionsStatus = 'Статус черновика обновлён.';
  } catch (error) {
    optimizationActionsStatus = error.message || 'Не удалось обновить черновик.';
  } finally {
    render();
  }
}


async function loadOptimizationExecutionPreview(actionId) {
  if (!selectedClientId || !actionId) return;
  optimizationExecutionPreviews = {
    ...optimizationExecutionPreviews,
    [actionId]: { loading: true, error: '', data: optimizationExecutionPreviews[actionId]?.data || null },
  };
  render();
  try {
    const payload = await optimizationService.fetchOptimizationExecutionPreview(selectedClientId, actionId);
    optimizationExecutionPreviews = {
      ...optimizationExecutionPreviews,
      [actionId]: { loading: false, error: '', data: normalizeOptimizationPreview(payload) },
    };
  } catch (error) {
    optimizationExecutionPreviews = {
      ...optimizationExecutionPreviews,
      [actionId]: { loading: false, error: error.message || 'Не удалось загрузить предпросмотр применения', data: null },
    };
  }
  render();
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

function renderBusinessContextPanel(compact = false) {
  const context = businessContextDraft || businessContext || defaultBusinessContext();
  const score = contextCompletenessScore(context);
  const field = (name, label, placeholder = '') => `
    <label class="businessContextField">
      <span>${label}</span>
      <textarea name="${name}" placeholder="${escapeHtml(placeholder)}" ${businessContextLoading || businessContextSaving ? 'disabled' : ''}>${escapeHtml(context[name] || '')}</textarea>
    </label>
  `;
  return `
    <section class="panel businessContextPanel ${compact ? 'compactBusinessContext' : ''}">
      <div class="panelHeader">
        <div>
          <h3>${compact ? 'Контекст бизнеса для AI' : 'Контекст бизнеса'}</h3>
          <p>${compact ? 'AI учитывает эти данные при аудите и рекомендациях.' : 'Заполните информацию о бизнесе, чтобы AI не давал generic-рекомендации.'}</p>
        </div>
        <div class="contextScore"><span>Заполнено</span><strong>${score}%</strong></div>
      </div>
      ${businessContextStatus ? `<div class="authStatus integrationStatus">${escapeHtml(businessContextStatus)}</div>` : ''}
      <form class="businessContextForm" data-business-context-form>
        <div class="businessContextGrid">
          ${field('companyName', 'Компания', 'Название клиента')}
          ${field('websiteUrl', 'Сайт', 'https://example.ru')}
          ${field('industry', 'Ниша', 'Например: медицина, недвижимость, e-commerce')}
          ${field('productDescription', 'Продукт / услуга', 'Что продаём и чем отличаемся')}
          ${field('targetAudience', 'Целевая аудитория', 'Кто покупает, сегменты, B2B/B2C')}
          ${field('geography', 'География', 'Города, регионы, ограничения доставки')}
          ${field('mainOffers', 'Основные офферы', 'Акции, преимущества, УТП')}
          ${field('conversionActions', 'Целевые действия', 'Заявка, звонок, бронь, покупка, квиз')}
          ${field('averageOrderValue', 'Средний чек / ценность лида', 'Средний чек, маржа, LTV или ценность заявки')}
          ${field('leadValueNotes', 'Заметки по ценности лида', 'Какие лиды качественные/некачественные')}
          ${field('businessConstraints', 'Ограничения бизнеса', 'Бюджет, склад, сроки, юридические ограничения')}
          ${field('negativeTopics', 'Нерелевантные темы / минус-направления', 'Запросы и темы, которые не подходят бизнесу')}
          ${field('landingPageNotes', 'Посадочные страницы и заметки', 'URL, структура, важные блоки. Автопроверки страниц пока нет.')}
          ${field('competitorNotes', 'Конкуренты', 'Конкуренты, отличие, ценовое позиционирование')}
          ${field('manualNotes', 'Ручные заметки специалиста', 'Что важно помнить при аудите и оптимизации')}
          ${field('memoryNotes', 'Память проекта', 'Сохранённые выводы AI и важные решения')}
          ${field('sourceNotes', 'Источники контекста', 'Откуда взята информация: клиент, бриф, звонок, CRM')}
        </div>
        <div class="authStatus integrationStatus">Автоматический анализ посадочных страниц будет добавлен отдельной итерацией. Сейчас контекст заполняется вручную.</div>
        <div class="heroActions">
          <button class="approveButton" type="submit" ${businessContextLoading ? 'disabled' : ''}>${businessContextLoading ? 'Сохраняем...' : 'Сохранить контекст'}</button>
          <button class="secondaryButton" type="button" data-reset-business-context>Очистить несохранённые изменения</button>
          <button class="secondaryButton" type="button" data-copy-text="${escapeHtml(businessContextCopyText(context))}">Скопировать контекст</button>
        </div>
      </form>
    </section>
  `;
}

function renderBusinessContext() {
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">🧭 Контекст бизнеса</span>
      <h2>Память проекта для AI-аналитика</h2>
      <p>Заполните бизнес-контекст один раз, чтобы AI учитывал бренд, нишу, офферы, ограничения и нерелевантные темы при анализе кампаний и поисковых запросов.</p>
    </div>
    ${renderBusinessContextPanel()}
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

function renderIntegrations() {
  const selectedClient = currentClient();
  const accounts = integrationStatus.accounts || [];
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">Интеграции</span><h2>Подключите Яндекс.Директ и Метрику</h2><p>OAuth-подключение хранится в backend. После подключения выберите аккаунт Яндекса для активного клиента.</p></div>
    <section class="panel integrationConnectPanel">
      <div class="panelHeader"><div><h3>Яндекс OAuth</h3><p>Нужен доступ к Директу и Метрике для синхронизации кампаний, расходов, целей и поисковых запросов.</p></div><button class="approveButton" data-integration="yandex-direct">Подключить Яндекс</button></div>
      <div class="authStatus integrationStatus">${escapeHtml(integrationStatus.message || 'Статус подключения ещё не проверен.')}</div>
      ${integrationStatus.connected ? `<div class="integrationSuccess">Подключено аккаунтов: ${accounts.length}</div>` : ''}
    </section>
    <section class="panel integrationConnectPanel">
      <div class="panelHeader"><div><h3>Привязка к клиенту</h3><p>Активный клиент: ${escapeHtml(selectedClient.name || 'не выбран')}. Direct login: ${escapeHtml(selectedClient.directLogin || 'не указан')}.</p></div><button class="secondaryButton" data-refresh-client-yandex ${selectedClient.id ? '' : 'disabled'}>Обновить</button></div>
      ${clientYandexStatus ? `<div class="authStatus integrationStatus">${escapeHtml(clientYandexStatus)}</div>` : ''}
      ${clientYandexLoading ? '<div class="authStatus integrationStatus">Загружаем доступные аккаунты...</div>' : ''}
      ${accounts.length ? `
        <div class="accountList">
          ${accounts.map((account) => {
            const selected = String(account.id) === String(clientYandexIntegration?.selected_account?.id || selectedClient.yandexAccountId || '');
            return `<article class="accountCard ${selected ? 'selected' : ''}"><div><strong>${escapeHtml(account.login || account.name || account.id)}</strong><span>${escapeHtml(account.id)}</span></div><button class="${selected ? 'secondaryButton' : 'approveButton'}" data-bind-yandex-account="${escapeHtml(account.id)}" ${selected ? 'disabled' : ''}>${selected ? 'Привязан' : 'Привязать'}</button></article>`;
          }).join('')}
        </div>
      ` : '<div class="authStatus integrationStatus">Нет доступных аккаунтов. Сначала подключите Яндекс OAuth.</div>'}
      ${clientYandexIntegration?.selected_account ? `<button class="dangerButton" data-unbind-yandex ${selectedClient.id ? '' : 'disabled'}>Отвязать аккаунт</button>` : ''}
    </section>
  `);
}

function renderAiStatusPanel() {
  const models = aiStatus.models || [];
  const selectedModelExists = models.some((model) => model.id === selectedAiModel);
  const modelOptions = [
    '<option value="openrouter/auto">openrouter/auto</option>',
    ...models.map((model) => `<option value="${escapeHtml(model.id)}" ${selectedAiModel === model.id ? 'selected' : ''}>${escapeHtml(model.name || model.id)}</option>`),
    `<option value="${CUSTOM_MODEL_VALUE}" ${selectedAiModel === CUSTOM_MODEL_VALUE || (!selectedModelExists && selectedAiModel !== 'openrouter/auto') ? 'selected' : ''}>Своя модель OpenRouter</option>`,
  ].join('');
  return `
    <section class="panel aiStatusPanel">
      <div class="panelHeader">
        <div><h3>OpenRouter</h3><p>${escapeHtml(aiStatus.message || 'Статус неизвестен')}</p></div>
        <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'Готов' : 'Нет ключа'}</span>
      </div>
      <div class="aiModelSettings">
        <label>Модель
          <select data-ai-model>${modelOptions}</select>
        </label>
        <label>Своя модель
          <input data-ai-custom-model value="${escapeHtml(customAiModel)}" placeholder="openai/gpt-4o" ${selectedAiModel === CUSTOM_MODEL_VALUE || !selectedModelExists ? '' : 'disabled'} />
        </label>
        <label>Профиль токенов
          <select data-ai-preset>
            <option value="economy" ${selectedAiPreset === 'economy' ? 'selected' : ''}>Economy · коротко и дёшево</option>
            <option value="balanced" ${selectedAiPreset === 'balanced' ? 'selected' : ''}>Balanced · больше контекста</option>
            <option value="deep" ${selectedAiPreset === 'deep' ? 'selected' : ''}>Deep · максимум деталей</option>
          </select>
        </label>
        <label>AI-context
          <select data-ai-max-tokens-mode>
            <option value="compact" ${aiMaxTokensMode === 'compact' ? 'selected' : ''}>Компактный</option>
            <option value="deep" ${aiMaxTokensMode === 'deep' ? 'selected' : ''}>Расширенный</option>
          </select>
        </label>
        <label>Tool results
          <select data-ai-tool-results-mode>
            <option value="summary" ${aiToolResultsMode === 'summary' ? 'selected' : ''}>Сводка</option>
            <option value="raw" ${aiToolResultsMode === 'raw' ? 'selected' : ''}>Сырые данные</option>
          </select>
        </label>
        <label>История чата
          <select data-ai-chat-history-limit>
            <option value="1" ${Number(aiChatHistoryLimit) === 1 ? 'selected' : ''}>1 сообщение</option>
            <option value="3" ${Number(aiChatHistoryLimit) === 3 ? 'selected' : ''}>3 сообщения</option>
            <option value="6" ${Number(aiChatHistoryLimit) === 6 ? 'selected' : ''}>6 сообщений</option>
          </select>
        </label>
        <label>Запросов Wordstat / Метрики
          <input data-ai-search-query-limit value="${escapeHtml(aiSearchQueryLimit)}" inputmode="numeric" />
        </label>
        <label class="checkboxLabel"><input type="checkbox" data-ai-compact-context ${aiCompactContext ? 'checked' : ''} /> Сжимать контекст</label>
      </div>
    </section>
  `;
}

function renderAiPromptDebugPanel() {
  return `
    <section class="panel aiPromptPanel">
      <div class="panelHeader">
        <div><h3>Prompt inspector</h3><p>Проверка размера контекста перед запросом к модели.</p></div>
        <button class="secondaryButton" data-ai-prompt-debug ${selectedClientId && !aiPromptDebugLoading ? '' : 'disabled'}>${aiPromptDebugLoading ? 'Проверяем...' : 'Проверить контекст'}</button>
      </div>
      ${aiPromptDebugError ? `<div class="authStatus integrationStatus">${escapeHtml(aiPromptDebugError)}</div>` : ''}
      ${aiPromptDebug ? `
        <div class="insightGrid">
          <article><span>Оценка токенов</span><strong>${formatNumberSafe(aiPromptDebug.estimated_tokens || 0)}</strong></article>
          <article><span>Лимит</span><strong>${formatNumberSafe(aiPromptDebug.target_context_tokens || 0)}</strong></article>
          <article><span>Tool calls</span><strong>${formatNumberSafe(aiPromptDebug.tool_calls || 0)}</strong></article>
        </div>
        <pre class="promptPreview">${escapeHtml(aiPromptDebug.prompt_preview || '')}</pre>
      ` : '<div class="authStatus integrationStatus">Пока нет данных. Нажмите «Проверить контекст».</div>'}
    </section>
  `;
}

function renderAiChat() {
  const campaignSelect = campaignOptions();
  return `
    <section class="panel aiChatPanel">
      <div class="panelHeader">
        <div><h3>AI-чат с MCP-инструментами</h3><p>Задавайте вопросы по Директу, Метрике, контексту и оптимизации. AI сам выберет нужные инструменты.</p></div>
        <span class="aiStatusBadge ${aiChatLoading ? 'pending' : 'ready'}">${aiChatLoading ? 'Думает' : 'Готов'}</span>
      </div>
      <div class="aiChatToolbar">
        <label>Кампания
          <select data-ai-chat-campaign>
            <option value="">Все кампании</option>
            ${campaignSelect.map((name) => `<option value="${escapeHtml(name)}" ${aiChatSelectedCampaignName === name ? 'selected' : ''}>${escapeHtml(name)}</option>`).join('')}
          </select>
        </label>
        <button class="secondaryButton" data-ai-chat-sample="Почему вырос CPA за последние 7 дней?">CPA</button>
        <button class="secondaryButton" data-ai-chat-sample="Какие поисковые запросы нужно добавить в минус-слова?">Минус-слова</button>
        <button class="secondaryButton" data-ai-chat-sample="Что в первую очередь проверить в Метрике и целях?">Метрика</button>
      </div>
      <div class="aiChatMessages">
        ${aiChatMessages.map((message) => `<article class="aiChatMessage ${message.role}"><span>${message.role === 'user' ? 'Вы' : 'AI'}</span><p>${escapeHtml(message.content)}</p></article>`).join('')}
      </div>
      ${aiChatError ? `<div class="authStatus integrationStatus">${escapeHtml(aiChatError)}${aiChatErrorDetails?.retry_suggestion ? `<br>${escapeHtml(aiChatErrorDetails.retry_suggestion)}` : ''}</div>` : ''}
      <form class="aiChatForm" data-ai-chat-form>
        <textarea name="message" placeholder="Например: почему CPA вырос и какие кампании проверить?">${escapeHtml(aiChatInput)}</textarea>
        <button class="approveButton" type="submit" ${aiChatLoading ? 'disabled' : ''}>${aiChatLoading ? 'Отправляем...' : 'Спросить AI'}</button>
      </form>
      ${aiChatToolTraces.length ? `
        <details class="toolTraceDetails"><summary>Использованные инструменты</summary>
          <div class="toolTraceList">${aiChatToolTraces.map((trace) => `<article><strong>${escapeHtml(trace.tool || 'tool')}</strong><pre>${escapeHtml(JSON.stringify(trace, null, 2))}</pre></article>`).join('')}</div>
        </details>
      ` : ''}
    </section>
  `;
}

function renderClientAiRecommendations() {
  return `
    <section class="panel aiRecommendationsPanel">
      <div class="panelHeader"><div><h3>AI-рекомендации по клиенту</h3><p>Генерируются с учётом синхронизации, бизнес-контекста и настроек токенов.</p></div><button class="approveButton" data-client-ai-recommendations ${selectedClientId && !aiRecommendationsLoading ? '' : 'disabled'}>${aiRecommendationsLoading ? 'Генерируем...' : 'Сформировать'}</button></div>
      ${aiRecommendationsError ? `<div class="authStatus integrationStatus">${escapeHtml(aiRecommendationsError)}</div>` : ''}
      ${clientAiRecommendations?.recommendations?.length ? `
        <div class="aiDraftGrid">
          ${clientAiRecommendations.recommendations.map((item) => `<article><span>${escapeHtml(item.priority || 'medium')}</span><h3>${escapeHtml(item.title || 'Рекомендация')}</h3><p>${escapeHtml(item.description || item.reason || '')}</p><small>${escapeHtml(item.expected_effect || item.effort || '')}</small></article>`).join('')}
        </div>
      ` : '<div class="authStatus integrationStatus">AI-рекомендаций пока нет.</div>'}
    </section>
  `;
}

function renderAiAssistant() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">AI-аналитик</span><h2>AI workspace для Директа и Метрики</h2><p>Настраивайте модель, проверяйте контекст, задавайте вопросы и генерируйте рекомендации по клиенту.</p></div>
    <div class="aiGrid">
      ${renderAiStatusPanel()}
      ${renderAiPromptDebugPanel()}
    </div>
    ${renderAiChat()}
    ${renderClientAiRecommendations()}
    <section class="panel aiQuickActions"><h3>Быстрые промпты</h3><div class="heroActions">
      <button class="secondaryButton" data-ai-prompt="audit" ${aiLoading ? 'disabled' : ''}>Аудит</button>
      <button class="secondaryButton" data-ai-prompt="recommendations" ${aiLoading ? 'disabled' : ''}>Рекомендации</button>
      <button class="secondaryButton" data-ai-prompt="report" ${aiLoading ? 'disabled' : ''}>Отчёт</button>
      <button class="secondaryButton" data-ai-prompt="questions" ${aiLoading ? 'disabled' : ''}>Вопросы клиенту</button>
    </div>${aiError ? `<div class="authStatus integrationStatus">${escapeHtml(aiError)}</div>` : ''}${aiResult ? `<pre class="aiResult">${escapeHtml(aiResult.text || aiResult.answer || JSON.stringify(aiResult, null, 2))}</pre>` : ''}</section>
  `);
}

function renderOptimizationPlanPanel() {
  const plan = optimizationPlan;
  return `
    <section class="panel optimizationPlanPanel">
      <div class="panelHeader"><div><h3>План оптимизации</h3><p>AI и backend формируют план на основе кампаний, CPA, целей и поисковых запросов.</p></div><div class="heroActions"><button class="secondaryButton" data-load-optimization-plan ${selectedClientId && !optimizationPlanLoading ? '' : 'disabled'}>${optimizationPlanLoading ? 'Формируем...' : 'Обновить план'}</button><button class="approveButton" data-create-optimization-drafts ${selectedClientId && plan && !optimizationActionsLoading ? '' : 'disabled'}>Сохранить как черновики</button></div></div>
      ${optimizationStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationStatus)}</div>` : ''}
      ${plan ? `
        <div class="optimizationGrid">
          <article><span>Сгенерировано</span><strong>${normalizeDate(plan.generatedAt)}</strong></article>
          <article><span>Рекомендации бюджета</span><strong>${formatNumberSafe(plan.dailyBudgetRecommendations.length)}</strong></article>
          <article><span>Корректировки устройств</span><strong>${formatNumberSafe(plan.deviceAdjustments.length)}</strong></article>
        </div>
        <div class="recommendationGrid">
          ${plan.dailyBudgetRecommendations.slice(0, 6).map((item) => `<article><div class="confidence">${formatPercent((item.confidence || 0) * 100)}</div><h3>${escapeHtml(item.campaign_name || item.campaignName || 'Кампания')}</h3><p>Бюджет: ${formatMoney(item.current_budget || item.currentBudget || 0)} → ${formatMoney(item.recommended_budget || item.recommendedBudget || 0)}</p><small>${escapeHtml(item.reason || '')}</small></article>`).join('')}
          ${plan.deviceAdjustments.slice(0, 6).map((item) => `<article><div class="confidence">${formatPercent((item.confidence || 0) * 100)}</div><h3>${escapeHtml(item.device || 'Устройство')}</h3><p>Корректировка: ${item.current_modifier ?? item.currentModifier ?? 0}% → ${item.recommended_modifier ?? item.recommendedModifier ?? 0}%</p><small>${escapeHtml(item.reason || '')}</small></article>`).join('')}
        </div>
      ` : '<div class="authStatus integrationStatus">План пока не сформирован. Нужна статистика по клиенту.</div>'}
    </section>
  `;
}

function renderOptimizationActionsPanel() {
  const actions = getFilteredOptimizationActions();
  return `
    <section class="panel optimizationActionsPanel">
      <div class="panelHeader"><div><h3>Черновики согласования</h3><p>Перед применением каждое действие проходит ревью специалиста.</p></div><div class="heroActions"><select data-optimization-action-filter><option value="all" ${optimizationActionFilter === 'all' ? 'selected' : ''}>Все</option><option value="draft" ${optimizationActionFilter === 'draft' ? 'selected' : ''}>Черновики</option><option value="approved" ${optimizationActionFilter === 'approved' ? 'selected' : ''}>Одобрено</option><option value="rejected" ${optimizationActionFilter === 'rejected' ? 'selected' : ''}>Отклонено</option></select><button class="secondaryButton" data-load-optimization-actions ${selectedClientId && !optimizationActionsLoading ? '' : 'disabled'}>${optimizationActionsLoading ? 'Загрузка...' : 'Обновить'}</button></div></div>
      ${optimizationActionsStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationActionsStatus)}</div>` : ''}
      ${actions.length ? `<div class="actionList">${actions.map((action) => {
        const preview = optimizationExecutionPreviews[action.id];
        return `<article class="optimizationAction ${action.status || 'draft'}"><div><span>${escapeHtml(compactStatusLabel(action.status || 'draft'))}</span><h3>${escapeHtml(action.title || action.entityName || action.actionType || 'Действие')}</h3><p>${escapeHtml(action.description || action.reason || '')}</p><small>${escapeHtml(action.entityType || '')} · ${escapeHtml(action.actionType || '')}</small></div><div class="actionButtons"><button class="secondaryButton" data-preview-optimization-action="${escapeHtml(action.id)}">Предпросмотр</button><button class="approveButton" data-update-optimization-action="${escapeHtml(action.id)}" data-status="approved">Одобрить</button><button class="dangerButton" data-update-optimization-action="${escapeHtml(action.id)}" data-status="rejected">Отклонить</button></div>${preview?.loading ? '<div class="authStatus integrationStatus">Загружаем предпросмотр...</div>' : ''}${preview?.error ? `<div class="authStatus integrationStatus">${escapeHtml(preview.error)}</div>` : ''}${preview?.data ? `<details class="toolTraceDetails" open><summary>Что будет применено</summary><pre>${escapeHtml(JSON.stringify(preview.data, null, 2))}</pre></details>` : ''}</article>`;
      }).join('')}</div>` : '<div class="authStatus integrationStatus">Черновиков пока нет.</div>'}
    </section>
  `;
}

function renderOptimization() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">Оптимизация</span><h2>Безопасное применение рекомендаций</h2><p>DirectPilot формирует черновики действий, показывает предпросмотр и ждёт согласования специалиста.</p></div>
    ${renderOptimizationPlanPanel()}
    ${renderOptimizationActionsPanel()}
  `);
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
  if (activeView === 'ai' && aiStatus.message === 'Статус OpenRouter ещё не загружен.') {
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
  if (event.target.matches('[data-ai-custom-model]')) customAiModel = event.target.value;
  if (event.target.matches('[data-ai-search-query-limit]')) aiSearchQueryLimit = event.target.value;
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
  if (event.target.matches('[data-ai-model]')) {
    selectedAiModel = event.target.value;
    if (selectedAiModel !== CUSTOM_MODEL_VALUE) customAiModel = event.target.value;
    render();
  }
  if (event.target.matches('[data-ai-preset]')) {
    selectedAiPreset = event.target.value;
    render();
  }
  if (event.target.matches('[data-ai-max-tokens-mode]')) {
    aiMaxTokensMode = event.target.value;
    render();
  }
  if (event.target.matches('[data-ai-tool-results-mode]')) {
    aiToolResultsMode = event.target.value;
    render();
  }
  if (event.target.matches('[data-ai-chat-history-limit]')) {
    aiChatHistoryLimit = Number(event.target.value) || 3;
    render();
  }
  if (event.target.matches('[data-ai-compact-context]')) {
    aiCompactContext = event.target.checked;
    render();
  }
  if (event.target.matches('[data-ai-chat-campaign]')) {
    aiChatSelectedCampaignName = event.target.value;
  }
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
        saveSession(authEmail, data.access_token);
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
    const formData = new FormData(clientForm);
    const name = formData.get('name')?.toString().trim();
    const directLogin = formData.get('directLogin')?.toString().trim();
    const metricaCounter = formData.get('metricaCounter')?.toString().trim();
    if (!name) return;
    const newClient = clientsStore.createClientFromForm(name, directLogin, metricaCounter);
    clientFormStatus = 'Сохраняем клиента...';
    render();
    try {
      if (backendClientsAvailable) {
        const payload = await clientsService.createClient({
          id: newClient.id,
          name: newClient.name,
          directLogin: newClient.directLogin,
          metricaCounter: newClient.metricaCounter,
          segment: newClient.segment,
        });
        accountClients = [...accountClients, clientsStore.normalizeBackendClient(payload)];
        clientFormStatus = 'Клиент сохранён в базе данных.';
      } else {
        accountClients = [...accountClients, newClient];
        clientFormStatus = 'Backend недоступен, клиент временно сохранён локально.';
      }
      selectedClientId = newClient.id;
      saveSelectedClientId(selectedClientId);
      clientsStore.saveStoredClients(accountClients);
      clientDraftName = '';
      clientDraftDirectLogin = '';
      clientDraftMetricaCounter = '';
    } catch (error) {
      accountClients = [...accountClients, newClient];
      selectedClientId = newClient.id;
      saveSelectedClientId(selectedClientId);
      clientsStore.saveStoredClients(accountClients);
      clientFormStatus = `${error.message}. Клиент сохранён локально.`;
    }
    render();
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

  const aiChatForm = event.target.closest('[data-ai-chat-form]');
  if (aiChatForm) {
    event.preventDefault();
    const message = new FormData(aiChatForm).get('message')?.toString();
    await sendAiChatMessage(message);
  }
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
    clientAiRecommendations = null;
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
  if (event.target.closest('[data-ai-prompt-debug]')) {
    await loadAiPromptDebug();
    return;
  }
  if (event.target.closest('[data-client-ai-recommendations]')) {
    await requestAiRecommendations();
    return;
  }
  const sampleButton = event.target.closest('[data-ai-chat-sample]');
  if (sampleButton) {
    aiChatInput = sampleButton.dataset.aiChatSample || '';
    render();
    return;
  }
  const promptButton = event.target.closest('[data-ai-prompt]');
  if (promptButton) {
    await generateAiInsight(aiPromptFor(promptButton.dataset.aiPrompt));
    return;
  }
  const integrationButton = event.target.closest('[data-integration="yandex-direct"]');
  if (integrationButton) {
    integrationStatus.message = 'Запрашиваем OAuth URL...';
    render();
    try {
      const payload = await integrationsService.startYandexOAuth();
      window.location.href = payload.auth_url;
    } catch (error) {
      integrationStatus = { ...integrationStatus, message: error.message || 'Не удалось начать подключение Яндекса.' };
      render();
    }
  }
});
async function loadIntegrationStatus() {
  try {
    const payload = await integrationsService.fetchYandexStatus();
    integrationStatus = {
      connected: Boolean(payload.connected),
      accounts: Array.isArray(payload.accounts) ? payload.accounts : [],
      message: payload.connected ? 'Яндекс подключён. Можно привязать аккаунт к клиенту.' : 'Яндекс ещё не подключён.',
    };
  } catch (error) {
    integrationStatus = { connected: false, accounts: [], message: 'Backend недоступен, статус Яндекса не проверен.' };
  }
  render();
}


async function loadClientYandexIntegration(force = false) {
  if (!selectedClientId || clientYandexLoading || (clientYandexIntegration && !force)) return;
  clientYandexLoading = true;
  clientYandexStatus = 'Загружаем привязку клиента к Яндексу...';
  render();
  try {
    const payload = await integrationsService.fetchClientYandexIntegration(selectedClientId);
    clientYandexIntegration = payload;
    clientYandexStatus = payload.selected_account ? 'Аккаунт Яндекса привязан к клиенту.' : 'Выберите аккаунт Яндекса для клиента.';
    if (payload.selected_account?.id) {
      accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, yandexAccountId: payload.selected_account.id } : client);
      clientsStore.saveStoredClients(accountClients);
    }
  } catch (error) {
    clientYandexStatus = error.message || 'Не удалось загрузить привязку Яндекса.';
  } finally {
    clientYandexLoading = false;
    render();
  }
}


async function bindClientYandexAccount(accountId) {
  if (!selectedClientId || !accountId) return;
  clientYandexLoading = true;
  clientYandexStatus = 'Привязываем аккаунт Яндекса к клиенту...';
  render();
  try {
    const payload = await integrationsService.bindClientYandexIntegration(selectedClientId, accountId);
    clientYandexIntegration = payload;
    accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, yandexAccountId: accountId } : client);
    clientsStore.saveStoredClients(accountClients);
    clientYandexStatus = 'Аккаунт Яндекса привязан к клиенту.';
  } catch (error) {
    clientYandexStatus = error.message || 'Не удалось привязать аккаунт.';
  } finally {
    clientYandexLoading = false;
    render();
  }
}


async function unbindClientYandexAccount() {
  if (!selectedClientId) return;
  clientYandexLoading = true;
  clientYandexStatus = 'Отвязываем аккаунт Яндекса...';
  render();
  try {
    const payload = await integrationsService.unbindClientYandexIntegration(selectedClientId);
    clientYandexIntegration = payload;
    accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, yandexAccountId: '' } : client);
    clientsStore.saveStoredClients(accountClients);
    clientYandexStatus = 'Аккаунт отвязан от клиента.';
  } catch (error) {
    clientYandexStatus = error.message || 'Не удалось отвязать аккаунт.';
  } finally {
    clientYandexLoading = false;
    render();
  }
}


function setClientSettingsDraftFromForm(form) {
  const formData = new FormData(form);
  clientSettingsDraft = {
    name: formData.get('name')?.toString().trim() || '',
    directLogin: formData.get('directLogin')?.toString().trim() || '',
    metricaCounter: formData.get('metricaCounter')?.toString().trim() || '',
    targetCpa: formData.get('targetCpa')?.toString().trim() || '',
    mainGoalId: formData.get('mainGoalId')?.toString().trim() || '',
    conversionGoalIds: formData.get('conversionGoalIds')?.toString().trim() || '',
    notes: formData.get('notes')?.toString().trim() || '',
  };
  return clientSettingsDraft;
}

async function saveClientSettings(form) {
  if (!selectedClientId) return;
  const draft = setClientSettingsDraftFromForm(form);
  clientSettingsSaving = true;
  clientSettingsStatus = 'Сохраняем настройки клиента...';
  render();
  const localUpdate = {
    name: draft.name,
    directLogin: draft.directLogin || 'Не подключен',
    metricaCounter: draft.metricaCounter || 'Не подключен',
    targetCpa: draft.targetCpa,
    mainGoalId: draft.mainGoalId,
    conversionGoalIds: draft.conversionGoalIds,
    notes: draft.notes,
  };
  try {
    if (backendClientsAvailable) {
      const payload = await clientsService.updateClient(selectedClientId, {
        name: draft.name,
        direct_login: draft.directLogin || null,
        metrica_counter: draft.metricaCounter || null,
        target_cpa: draft.targetCpa ? Number(draft.targetCpa) : null,
        main_goal_id: draft.mainGoalId || null,
        conversion_goal_ids: draft.conversionGoalIds || null,
        notes: draft.notes || null,
      });
      accountClients = accountClients.map((client) => client.id === selectedClientId ? clientsStore.normalizeBackendClient(payload) : client);
      clientSettingsStatus = 'Настройки клиента сохранены в базе.';
    } else {
      accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, ...localUpdate } : client);
      clientSettingsStatus = 'Backend недоступен, настройки сохранены локально.';
    }
    clientsStore.saveStoredClients(accountClients);
    clientSettingsDraft = null;
    businessContext = null;
    perfSummary = null;
    optimizationPlan = null;
  } catch (error) {
    accountClients = accountClients.map((client) => client.id === selectedClientId ? { ...client, ...localUpdate } : client);
    clientsStore.saveStoredClients(accountClients);
    clientSettingsStatus = `${error.message}. Локальная копия обновлена.`;
  } finally {
    clientSettingsSaving = false;
    render();
  }
}


async function deleteClient(clientId) {
  if (!clientId) return;
  if (!window.confirm('Удалить клиента? Это действие нельзя отменить.')) return;
  clientSettingsStatus = 'Удаляем клиента...';
  render();
  try {
    if (backendClientsAvailable) {
      await clientsService.deleteClient(clientId);
    }
    accountClients = accountClients.filter((client) => client.id !== clientId);
    selectedClientId = accountClients[0]?.id || '';
    if (selectedClientId) saveSelectedClientId(selectedClientId);
    clientsStore.saveStoredClients(accountClients);
    clientSettingsStatus = accountClients.length ? 'Клиент удалён.' : 'Клиент удалён. Создайте нового клиента.';
    activeView = 'clients';
  } catch (error) {
    clientSettingsStatus = error.message || 'Не удалось удалить клиента.';
  } finally {
    render();
  }
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

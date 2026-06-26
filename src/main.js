import {
  API_BASE,
  apiFetch,
  clearApiCache,
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
import { createClientId } from './core/ids.js';
import { requestEmailCode, verifyEmailCode } from './core/session-api.js';
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
let apiBaseDraft = API_BASE;
let pendingEditableFocusTarget = null;
let authEmail = '';
let authStatus = '';
let authStep = 'email';
let authCode = '';
let authLoading = false;
let devCode = null;
let integrationStatus = {};
let clientYandexIntegration = null;
let clientYandexLoading = false;
let clientYandexStatus = oauthReturnStatus === 'connected'
  ? 'Яндекс-аккаунт подключён. Теперь выберите его и привяжите к клиенту.'
  : oauthReturnStatus === 'missing_code'
    ? 'Яндекс OAuth не вернул код подтверждения. Попробуйте подключить аккаунт ещё раз.'
    : oauthReturnStatus === 'error'
      ? 'Не удалось завершить подключение Яндекса. Попробуйте начать подключение из приложения ещё раз.'
      : '';
let clientYandexLoadedFor = '';
let accountClients = loadAccountClients();
let aiStatus = { models: [], configured: false, message: 'Статус OpenRouter ещё не загружен.' };
const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';
let aiModel = 'openrouter/auto';
let aiCustomModel = 'openai/gpt-4o';
let aiPreset = 'economy';
let aiMaxTokensMode = 'compact';
let aiCompactContext = true;
let aiToolResultsMode = 'summary';
let aiChatHistoryLimit = 3;
let aiSearchQueryLimit = '20';
let aiPrompt = 'Проанализируй выбранного клиента DirectPilot AI: какие данные нужны из Яндекс.Директа и Метрики, чтобы сформировать первые рекомендации?';
let aiResponse = null;
let aiError = '';
let aiLoading = false;
let aiModelTestLoading = false;
let aiModelTestStatus = '';
let aiPromptDebugLoading = false;
let aiPromptDebugStatus = '';
let aiPromptDebugSnapshot = null;
let aiRequestInspectorEnabled = false;
let openrouterRequestDebug = null;
let clientAiRecommendations = null;
let clientAiLoading = false;
let clientAiError = '';
let clientFormStatus = '';
let clientDraftName = '';
let clientDraftDirectLogin = '';
let clientDraftMetricaCounter = '';
let syncStatusMessage = '';
let syncLoading = false;
let perfSummary = null;
let perfLoading = false;
let syncJobs = [];
let syncJobsLoading = false;
let syncJobsStatus = '';
let optimizationPlan = null;
let optimizationPlanLoading = false;
let optimizationPlanStatus = '';
let optimizationFilter = 'all';
const optimizationPlanByClientId = {};
let optimizationActions = [];
let optimizationActionsLoading = false;
let optimizationActionsStatus = '';
let optimizationActionFilter = 'all';
let optimizationActionsLoadedFor = '';
const optimizationActionsByClientId = {};
const optimizationActionFilterByClientId = {};
const optimizationExecutionPreviewsByActionId = {};
let optimizationExecutionPreviewStatus = '';
let businessContext = null;
let businessContextLoading = false;
let businessContextStatus = '';
let businessContextLoadedFor = '';
let clientsLoaded = false;
let backendClientsAvailable = false;
let backendClientsStatus = 'Проверяем подключение backend...';
const initialAiChatMessage = { role: 'assistant', content: 'Здравствуйте! Я AI-аналитик DirectPilot. Спросите про Директ, Метрику, CPA, цели или рекомендации — я соберу данные через MCP-инструменты и отвечу по контексту.' };
let aiChatMessages = [{ ...initialAiChatMessage }];
let aiChatInput = 'Почему растёт CPA и что проверить в Яндекс.Метрике?';
let aiChatLoading = false;
let aiChatError = '';
let aiChatErrorDetails = null;
let aiChatToolTraces = [];
let selectedAiCampaignName = '';
const clientAiRecommendationsByClientId = {};
const aiChatStateByClientId = {};
let lastAiAction = null;

let selectedClientId = window.localStorage.getItem(scopedStorageKey('directpilot_selected_client_id')) || accountClients[0]?.id || '';




function saveSelectedClientId() {
  if (selectedClientId) {
    localStorage.setItem(scopedStorageKey('directpilot_selected_client_id'), selectedClientId);
  } else {
    localStorage.removeItem(scopedStorageKey('directpilot_selected_client_id'));
  }
}

async function loadClientsFromApi() {
  if (clientsLoaded) return;
  clientsLoaded = true;
  const previousSelectedClientId = selectedClientId;
  try {
    const response = await apiFetch('/clients');
    if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
    const payload = await response.json();
    if (!Array.isArray(payload)) throw new Error('Invalid clients payload');

    backendClientsAvailable = true;
    backendClientsStatus = response.headers.get('X-DirectPilot-Cache')
      ? 'Backend режим: клиенты показаны из быстрого кэша, свежие данные обновляются в фоне.'
      : 'Backend режим: клиенты загружаются из API.';
    accountClients = payload;
    if (!selectedClientId || !accountClients.some((client) => client.id === selectedClientId)) {
      selectedClientId = accountClients[0]?.id || '';
    }
    saveSelectedClientId();
    if (selectedClientId !== previousSelectedClientId) {
      resetClientDerivedState();
      resetSelectedClientOperationalState();
    }
    saveAccountClients();
    render();
  } catch (error) {
    if (error.message === 'Authentication required') return;
    backendClientsAvailable = false;
    backendClientsStatus = 'Backend недоступен. Включён demo/fallback режим (данные из localStorage).';
    accountClients = loadAccountClients();
    if (!selectedClientId || !accountClients.some((client) => client.id === selectedClientId)) {
      selectedClientId = accountClients[0]?.id || '';
    }
    saveSelectedClientId();
    if (selectedClientId !== previousSelectedClientId) {
      resetClientDerivedState();
      resetSelectedClientOperationalState();
    }
    render();
  }
}

async function createClientOnApi(client) {
  const response = await apiFetch('/clients', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: client.id,
      name: client.name,
      direct_login: client.directLogin === 'Не подключен' ? null : client.directLogin,
      metrica_counter: client.metricaCounter === 'Не подключен' ? null : client.metricaCounter,
      yandex_account_id: client.yandexAccountId || null,
      target_cpa: client.targetCpa || null,
      main_goal_id: client.mainGoalId || null,
      conversion_goal_ids: client.conversionGoalIds || client.mainGoalId || null,
      notes: client.notes || null,
      segment: client.segment,
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить клиента в базе данных');
  return payload;
}

async function updateClientOnApi(clientId, values) {
  const response = await apiFetch(`/clients/${clientId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(values),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить настройки клиента');
  return payload;
}

async function deleteClientOnApi(clientId) {
  const response = await apiFetch(`/clients/${clientId}`, { method: 'DELETE' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось удалить клиента');
  return payload;
}

function emptyClient() {
  return {
    id: '',
    name: 'Клиент не выбран',
    segment: 'Добавьте клиента',
    spend: '—',
    leads: 0,
    cpa: '—',
    roas: '—',
    trend: 'Нет подключённых аккаунтов',
    score: 0,
    status: 'Ожидает подключения',
    directLogin: 'Не подключен',
    metricaCounter: 'Не подключен',
  };
}

function loadAccountClients() {
  try {
    const saved = JSON.parse(localStorage.getItem(scopedStorageKey('directpilot_clients')) || '[]');
    return Array.isArray(saved) ? saved : initialClients;
  } catch (error) {
    return initialClients;
  }
}

function saveAccountClients() {
  localStorage.setItem(scopedStorageKey('directpilot_clients'), JSON.stringify(accountClients));
}

function isEditingTextField() {
  const element = document.activeElement;
  return Boolean(element?.matches?.('input, textarea, select'));
}

function isPlainTextInputTarget(target) {
  return Boolean(target?.closest?.('input, textarea, select, label'));
}

function getViewActionTarget(target) {
  const viewTarget = target?.closest?.('[data-view]');
  if (!viewTarget || viewTarget === document.body) return null;
  return viewTarget;
}

function isInteractiveActionTarget(target) {
  return Boolean(
    target?.closest?.('button, a, [role="button"], [data-save-api-base], [data-client-id], [data-integration], [data-client-ai-recommendations], [data-sync-client], [data-load-summary], [data-load-sync-jobs], [data-load-optimization-plan], [data-load-optimization-actions], [data-save-optimization-actions], [data-update-optimization-action], [data-load-execution-preview], [data-copy-optimization-plan], [data-copy-text], [data-optimization-filter], [data-optimization-action-filter], [data-ai-quick-action], [data-ai-economy-fallback], [data-ai-reduction-action], [data-openrouter-inspector], [data-copy-openrouter-debug], [data-copy-ai-trace], [data-test-ai-model], [data-check-ai-prompt-size], [data-clear-ai-chat], [data-refresh-yandex-status], [data-go-view], [data-logout]')
    || getViewActionTarget(target)
  );
}

function getEditableFieldTarget(target) {
  const field = target?.closest?.('input, textarea, select');
  if (!field) return null;
  if (field.disabled || field.readOnly) return null;
  return field;
}

function makeClientId(name) {
  const slug = name.toLowerCase().replace(/[^a-z0-9а-яё]+/gi, '-').replace(/^-|-$/g, '').slice(0, 32);
  return createClientId(slug || 'client');
}

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
const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
const API_BASE = resolveApiBase();
const page = document.body.dataset.page ?? 'landing';
const currentEmail = (window.localStorage.getItem('directpilot_email') || '').trim().toLowerCase();

if (page === 'app' && !getSessionToken()) {
  window.location.href = 'login.html';
  throw new Error('Authentication required');
}

function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');
  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000/api/v1';
  }
  if (hostname === 'maximusb93.github.io') {
    return DEFAULT_PRODUCTION_API_BASE;
  }
  return `${origin}/api/v1`;
}

function hasCustomApiBase() {
  return Boolean(window.localStorage.getItem('directpilot_api_base')?.trim());
}

function getSessionToken() {
  return window.localStorage.getItem('directpilot_session') || '';
}

function scopedStorageKey(key) {
  return currentEmail ? `${key}_${currentEmail}` : key;
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401) {
    localStorage.removeItem('directpilot_session');
    localStorage.removeItem('directpilot_email');
    window.location.href = 'login.html';
    throw new Error('Authentication required');
  }
  return response;
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
let aiPrompt = 'Проанализируй выбранного клиента DirectPilot AI: какие данные нужны из Яндекс.Директа и Метрики, чтобы сформировать первые рекомендации?';
let aiResponse = null;
let aiError = '';
let aiLoading = false;
let aiModelTestLoading = false;
let aiModelTestStatus = '';
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
    backendClientsStatus = 'Backend режим: клиенты загружаются из API.';
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
    target?.closest?.('button, a, [role="button"], [data-save-api-base], [data-client-id], [data-integration], [data-client-ai-recommendations], [data-sync-client], [data-load-summary], [data-load-sync-jobs], [data-load-optimization-plan], [data-load-optimization-actions], [data-save-optimization-actions], [data-update-optimization-action], [data-load-execution-preview], [data-copy-optimization-plan], [data-copy-text], [data-optimization-filter], [data-optimization-action-filter], [data-ai-quick-action], [data-ai-economy-fallback], [data-test-ai-model], [data-clear-ai-chat], [data-refresh-yandex-status], [data-go-view], [data-logout]')
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
  return `${slug || 'client'}-${Date.now().toString(36)}`;
}

function getConfiguredAiModelIds() {
  return aiStatus.models?.map((model) => model.id) || [];
}

function isCustomAiModel() {
  const configuredIds = getConfiguredAiModelIds();
  if (configuredIds.length === 0) return false;
  return Boolean(aiModel && !configuredIds.includes(aiModel));
}

function activeAiModel() {
  return (isCustomAiModel() ? aiCustomModel : aiModel).trim() || aiStatus.default_model || 'openrouter/auto';
}

function getAiModelSettingsKey() {
  return scopedStorageKey('directpilot_ai_model_settings');
}

function loadAiModelSettings() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(getAiModelSettingsKey()) || '{}');
    if (saved.selectedModel) aiModel = String(saved.selectedModel);
    if (saved.selectedPreset) aiPreset = String(saved.selectedPreset);
    if (saved.customModel) aiCustomModel = String(saved.customModel);
    if (saved.maxTokensMode) aiMaxTokensMode = String(saved.maxTokensMode);
  } catch (error) {
    window.localStorage.removeItem(getAiModelSettingsKey());
  }
}

function saveAiModelSettings() {
  window.localStorage.setItem(getAiModelSettingsKey(), JSON.stringify({
    selectedModel: aiModel,
    selectedPreset: aiPreset,
    customModel: aiCustomModel,
    maxTokensMode: aiMaxTokensMode,
  }));
}

function recommendedAiModelOptions() {
  return [
    { id: 'openai/gpt-4.1-mini', label: 'OpenAI GPT-4.1 Mini', cost_tier: 'low', recommended_for: ['Эконом', 'регулярные проверки'] },
    { id: 'google/gemini-2.0-flash-001', label: 'Google Gemini 2.0 Flash', cost_tier: 'low', recommended_for: ['Эконом', 'быстрый аудит'] },
    { id: 'deepseek/deepseek-chat', label: 'DeepSeek Chat', cost_tier: 'low', recommended_for: ['Эконом', 'чат'] },
    { id: 'qwen/qwen-2.5-72b-instruct', label: 'Qwen 2.5 72B Instruct', cost_tier: 'low', recommended_for: ['Эконом', 'структурные ответы'] },
    { id: 'openai/gpt-4.1', label: 'OpenAI GPT-4.1', cost_tier: 'medium', recommended_for: ['Баланс', 'анализ кампаний'] },
    { id: 'anthropic/claude-3.5-sonnet', label: 'Claude 3.5 Sonnet', cost_tier: 'medium', recommended_for: ['Баланс', 'разбор гипотез'] },
    { id: 'google/gemini-2.5-pro', label: 'Google Gemini 2.5 Pro', cost_tier: 'medium', recommended_for: ['Баланс', 'глубокий аудит'] },
    { id: 'deepseek/deepseek-r1', label: 'DeepSeek R1', cost_tier: 'medium', recommended_for: ['Баланс', 'логический анализ'] },
    { id: 'anthropic/claude-3.7-sonnet', label: 'Claude 3.7 Sonnet', cost_tier: 'high', recommended_for: ['Максимум', 'сложный аудит'] },
    { id: 'openai/o3-mini', label: 'OpenAI o3-mini', cost_tier: 'high', recommended_for: ['Максимум', 'спорные выводы'] },
  ];
}

function getAiModelOptions() {
  const seen = new Set();
  return [...(aiStatus.models || []), ...recommendedAiModelOptions()].filter((model) => {
    if (!model?.id || seen.has(model.id)) return false;
    seen.add(model.id);
    return true;
  });
}

function getAiPresetOptions() {
  return aiStatus.presets?.length ? aiStatus.presets : [
    { id: 'economy', label: 'Эконом', purpose: 'Быстрые вопросы и первичный анализ', max_tokens: 1200, cost_tier: 'low' },
    { id: 'balanced', label: 'Баланс', purpose: 'Обычный анализ кампаний', max_tokens: 2500, cost_tier: 'medium' },
    { id: 'advanced', label: 'Максимум', purpose: 'Глубокий анализ и сложные рекомендации', max_tokens: 5000, cost_tier: 'high', warning: 'Может быть дороже' },
  ];
}

function activeAiPresetInfo() {
  return getAiPresetOptions().find((preset) => preset.id === aiPreset) || getAiPresetOptions()[0];
}

function aiPresetGuidance(presetId) {
  return {
    economy: 'Эконом — быстрые и дешёвые регулярные проверки.',
    balanced: 'Баланс — основной режим для анализа кампаний и запросов.',
    advanced: 'Максимум — сложные аудиты, спорные выводы, глубокий разбор.',
    custom: 'Своя модель — используйте только если понимаете стоимость и лимиты OpenRouter.',
  }[presetId] || '';
}

function aiPresetLabel(preset) {
  return { economy: 'Эконом', balanced: 'Баланс', advanced: 'Максимум', custom: 'Своя модель' }[preset?.id || preset] || preset?.label || preset;
}

function activeAiModelInfo() {
  const modelId = activeAiModel();
  return getAiModelOptions().find((model) => model.id === modelId) || {
    id: modelId,
    label: modelId,
    cost_tier: isCustomAiModel() ? 'unknown' : 'unknown',
    recommended_for: ['Своя модель OpenRouter'],
  };
}

function activeAiMaxTokens() {
  const cap = Number(activeAiPresetInfo()?.max_tokens || 1200);
  const factors = { compact: 0.5, normal: 0.8, detailed: 1 };
  return Math.max(1, Math.round(cap * (factors[aiMaxTokensMode] || 0.5)));
}

function aiRequestOptions() {
  return {
    model: activeAiModel(),
    ai_preset: aiPreset === 'custom' ? 'economy' : aiPreset,
    max_tokens: activeAiMaxTokens(),
  };
}

function normalizeAiErrorPayload(payload, fallbackMessage) {
  if (payload?.error) {
    return {
      message: payload.message || fallbackMessage,
      code: payload.error_code || '',
      model: payload.model || activeAiModel(),
      retryable: Boolean(payload.retryable),
      suggestedPreset: payload.suggested_preset || 'economy',
    };
  }
  const detail = payload?.detail;
  const rawMessage = typeof detail === 'string' ? detail : JSON.stringify(detail || payload || {});
  if (rawMessage.includes('429') || rawMessage.toLowerCase().includes('rate')) {
    return {
      message: 'Выбранная AI-модель временно перегружена или ограничена по лимитам. Выберите другую модель или повторите позже.',
      code: 'openrouter_rate_limited',
      model: activeAiModel(),
      retryable: true,
      suggestedPreset: 'economy',
    };
  }
  return {
    message: rawMessage || fallbackMessage,
    code: '',
    model: activeAiModel(),
    retryable: false,
    suggestedPreset: '',
  };
}

function applyEconomyFallback() {
  aiPreset = 'economy';
  aiModel = aiStatus.recommended_default_model || aiStatus.default_model || aiStatus.models?.[0]?.id || 'openai/gpt-4o-mini';
  aiMaxTokensMode = 'compact';
  saveAiModelSettings();
}

loadAiModelSettings();

function currentClient() {
  return accountClients.find((client) => client.id === selectedClientId) ?? accountClients[0] ?? emptyClient();
}

function getSelectedClient() {
  return currentClient();
}

function formatNumberSafe(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? new Intl.NumberFormat('ru-RU').format(number) : '0';
}

function formatMoneySafe(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(number)} ₽` : '0 ₽';
}

function formatPercentSafe(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? `${number.toFixed(2)}%` : '0.00%';
}

function formatDateSafe(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('ru-RU');
}

function conversionSourceLabel(source) {
  return {
    yandex_direct_goals: 'Цели Директа',
    yandex_direct_total: 'Общие конверсии Директа',
    fallback_total_when_goal_unavailable: 'Данные по выбранным целям недоступны',
    metrika_goal: 'Цель Метрики',
    metrika_goals: 'Цели Метрики',
    metrika_goal_unavailable: 'Данные Метрики недоступны',
    unavailable: 'Данные по целям недоступны',
    unknown: 'Нет данных',
  }[source] || source || 'Нет данных';
}

function issueFlagLabel(flag) {
  return {
    spend_without_conversions: 'Расход без конверсий',
    high_cpa: 'CPA выше цели',
    low_ctr: 'Низкий CTR',
    low_data: 'Мало данных',
    inefficient_spend_share: 'Неэффективная доля расхода',
    promising_campaign: 'Перспективная кампания',
    candidate_negative_keyword: 'Кандидат в минус-слова',
    costly_no_goal_conversion: 'Расход без целевых конверсий',
    low_relevance: 'Низкая релевантность',
    check_queries_landing_goals: 'Проверить запросы, посадочную и цели',
  }[flag] || flag || '—';
}

function renderIssueFlags(flags) {
  const normalized = Array.isArray(flags) ? flags : [];
  return normalized.length ? normalized.map(issueFlagLabel).join(', ') : '—';
}

function humanizeDataWarning(message) {
  const value = String(message || '');
  if (value.includes('Direct goal conversions unavailable') || value.includes('fallback_total_when_goal_unavailable')) {
    return 'Директ не вернул данные по выбранным целям. Проверьте ID целей и запустите синхронизацию повторно.';
  }
  return value;
}

function auditStatusLabel(status) {
  return {
    pass: 'Ок',
    warning: 'Требует внимания',
    fail: 'Проблема',
    na: 'Нужны дополнительные данные',
  }[status] || status || '—';
}

function auditSourceLabel(source) {
  return source === 'needs_more_data' ? 'нужны дополнительные данные' : 'данные DirectPilot';
}

function auditGradeLabel(grade) {
  return grade === 'N/A' ? 'Нужны данные' : (grade || '—');
}

function actionSourceLabel(source) {
  return {
    rule_based: 'Правила DirectPilot',
    ai: 'AI',
    manual: 'Вручную',
    deterministic_fallback: 'Правила DirectPilot',
  }[source] || 'Черновик';
}

function severityLabel(severity) {
  return {
    critical: 'Критично',
    warning: 'Требует внимания',
    info: 'Информация',
    ok: 'Ок',
    low: 'Низкий',
    medium: 'Средний',
    high: 'Высокий',
  }[severity] || severity || 'Информация';
}

function renderActionButton(label, attributes = '', variant = 'secondary') {
  const className = variant === 'primary' ? 'approveButton' : 'secondaryButton';
  return `<button class="${className}" type="button" ${attributes}>${escapeHtml(label)}</button>`;
}

function hasClientValue(value) {
  return Boolean(value && value !== 'Не подключен' && value !== '—');
}

function hasPerformanceData() {
  return Boolean(perfSummary?.campaigns?.length || Number(perfSummary?.totals?.clicks || 0) > 0);
}

function canRunSync() {
  const client = getSelectedClient();
  return Boolean(client.id && hasClientValue(client.directLogin) && clientYandexIntegration?.connected);
}

function canRunAiAnalysis() {
  return Boolean(getSelectedClient().id && hasPerformanceData());
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

function badgeClassForStatus(status) {
  return status === 'ready' || status === 'approved' || status === 'reviewed' ? 'ready' : 'pending';
}

function getOptimizationActionCounts(actions = optimizationActions) {
  return actions.reduce((counts, action) => {
    counts.total += 1;
    counts[action.status] = (counts[action.status] || 0) + 1;
    return counts;
  }, { total: 0, draft: 0, reviewed: 0, approved: 0, rejected: 0, needs_changes: 0 });
}

function optimizationStatusLabel(status) {
  return {
    draft: 'Черновик',
    reviewed: 'Просмотрено',
    approved: 'Одобрено',
    rejected: 'Отклонено',
    needs_changes: 'Нужны правки',
  }[status] || status || 'Черновик';
}

function formatSyncStatus(value) {
  return {
    never_synced: 'Синхронизация ещё не запускалась',
    no_connection: 'Нет подключения к данным',
    no_data: 'Нет сохранённых данных',
    ok: 'Данные загружены',
    error: 'Ошибка синхронизации',
  }[value || 'never_synced'] || value || 'Неизвестно';
}

function getReadinessState() {
  const client = getSelectedClient();
  const hasClient = Boolean(client.id);
  const directReady = hasClientValue(client.directLogin);
  const metricaReady = hasClientValue(client.metricaCounter);
  const yandexBound = Boolean(clientYandexIntegration?.connected);
  const firstSyncDone = Boolean(client.lastSyncedAt || client.syncVersion > 0);
  const statsReady = hasPerformanceData();
  const aiReady = Boolean(clientAiRecommendationsByClientId[client.id] || clientAiRecommendations);

  return [
    { status: getSessionToken() ? 'ready' : 'blocked', label: 'Пользователь авторизован', description: currentEmail || 'Нет активной сессии', nextAction: 'Войдите по email', targetView: 'login' },
    { status: backendClientsAvailable ? 'ready' : 'pending', label: 'Backend API подключён', description: backendClientsStatus, nextAction: 'Проверьте Backend API URL', targetView: 'integrations' },
    { status: hasClient ? 'ready' : 'action_needed', label: 'Клиент выбран', description: hasClient ? client.name : 'Нет клиента', nextAction: 'Добавьте клиента', targetView: 'clients' },
    { status: !hasClient ? 'blocked' : directReady ? 'ready' : 'action_needed', label: 'Direct login указан', description: directReady ? client.directLogin : 'Укажите логин Яндекс.Директа в настройках клиента.', nextAction: 'Укажите Direct login', targetView: 'clients' },
    { status: !hasClient ? 'blocked' : metricaReady ? 'ready' : 'action_needed', label: 'Счётчик Метрики указан', description: metricaReady ? client.metricaCounter : 'Укажите ID счётчика Метрики.', nextAction: 'Укажите счётчик Метрики', targetView: 'clients' },
    { status: !hasClient ? 'blocked' : yandexBound ? 'ready' : 'action_needed', label: 'Яндекс-аккаунт привязан', description: yandexBound ? 'Аккаунт привязан к выбранному клиенту.' : 'Яндекс-аккаунт не привязан к этому клиенту.', nextAction: 'Привяжите Яндекс-аккаунт', targetView: 'integrations' },
    { status: !canRunSync() && !firstSyncDone ? 'blocked' : firstSyncDone ? 'ready' : 'action_needed', label: 'Первая синхронизация выполнена', description: formatSyncStatus(client.syncStatus), nextAction: 'Запустите синхронизацию', targetView: 'dashboard' },
    { status: statsReady ? 'ready' : firstSyncDone ? 'action_needed' : 'pending', label: 'Статистика кампаний доступна', description: statsReady ? `${perfSummary.campaigns.length} кампаний в сводке` : 'Нет сохранённых данных', nextAction: 'Обновите сводку или синхронизацию', targetView: 'dashboard' },
    { status: !hasClient ? 'blocked' : client.mainGoalId ? 'ready' : 'action_needed', label: 'ID основной цели указан', description: client.mainGoalId || 'Цель не выбрана. CPA будет считаться по общим конверсиям Директа.', nextAction: 'Укажите ID основной цели в настройках клиента', targetView: 'clients' },
    { status: !client.mainGoalId ? 'pending' : perfSummary?.hasGoalData ? 'ready' : 'action_needed', label: 'Конверсии по цели загружены', description: perfSummary?.hasGoalData ? 'Данные по выбранным целям Директа загружены' : 'Цель указана, но конверсии по ней ещё не загружены', nextAction: 'Запустите синхронизацию и проверьте цели', targetView: 'dashboard' },
    { status: aiReady ? 'ready' : statsReady ? 'action_needed' : 'pending', label: 'AI-анализ сгенерирован', description: aiReady ? 'AI-план готов для ревью.' : 'AI-анализ станет доступнее после загрузки статистики.', nextAction: 'Откройте AI-аналитик', targetView: 'ai' },
  ];
}

function getNextBestAction() {
  const item = getReadinessState().find((entry) => entry.status === 'action_needed' || entry.status === 'blocked' || entry.status === 'pending');
  return item || { status: 'ready', label: 'MVP поток готов', nextAction: 'Откройте AI-аналитик', targetView: 'ai' };
}

function resetClientDerivedState() {
  const clientId = selectedClientId || currentClient().id;
  clientAiRecommendations = clientAiRecommendationsByClientId[clientId] || null;
  clientAiError = '';
  const chatState = aiChatStateByClientId[clientId];
  aiChatMessages = chatState?.messages ? [...chatState.messages] : [{ ...initialAiChatMessage }];
  aiChatInput = chatState?.input || 'Почему растёт CPA и что проверить в Яндекс.Метрике?';
  aiChatError = '';
  aiChatErrorDetails = chatState?.errorDetails || null;
  aiChatToolTraces = chatState?.toolTraces ? [...chatState.toolTraces] : [];
  selectedAiCampaignName = chatState?.selectedCampaignName || '';
}

function saveActiveAiState() {
  if (!selectedClientId) return;
  if (clientAiRecommendations) {
    clientAiRecommendationsByClientId[selectedClientId] = clientAiRecommendations;
  }
  aiChatStateByClientId[selectedClientId] = {
    messages: [...aiChatMessages],
    input: aiChatInput,
    toolTraces: [...aiChatToolTraces],
    selectedCampaignName: selectedAiCampaignName,
    errorDetails: aiChatErrorDetails,
  };
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderBackendApiConfig() {
  const githubPagesWarning = window.location.hostname === 'maximusb93.github.io' && API_BASE.includes('github.io/api/v1')
    ? '<div class="authStatus aiError">GitHub Pages не содержит backend. Укажите Vercel backend URL.</div>'
    : '';

  return `
    <section class="panel backendApiConfig">
      <div class="panelHeader">
        <div>
          <h3>Backend API URL</h3>
          <p>Текущий Backend API URL: <code>${escapeHtml(API_BASE)}</code></p>
        </div>
      </div>
      ${githubPagesWarning}
      <div class="authForm" data-api-base-config>
        <div class="authField">
          <label for="backend-api-base">Backend API URL</label>
          <input id="backend-api-base" type="text" data-api-base-input data-debug-name="backend-api-base" value="${escapeHtml(apiBaseDraft)}" placeholder="https://your-backend.vercel.app/api/v1" autocomplete="url" />
        </div>
        <button class="secondaryButton" type="button" data-save-api-base>Сохранить backend URL</button>
      </div>
    </section>
  `;
}

function priorityLabel(priority) {
  return {
    high: 'Высокий',
    medium: 'Средний',
    low: 'Низкий',
  }[priority];
}

function metricCard(metric) {
  return `
    <article class="metricCard">
      <span>${metric.label}</span>
      <strong>${metric.value}</strong>
      <small>${metric.delta}</small>
    </article>
  `;
}

function renderLanding() {
  return `
    <nav class="nav landingNav">
      <a class="brand" href="#" data-view="landing" aria-label="DirectPilot AI">
        <span class="brandIcon">✦</span>
        DirectPilot AI
      </a>
      <div class="navLinks" aria-label="Главная навигация">
        <a href="#features">Возможности</a>
        <a href="#workflow">Как работает</a>
        <a href="#security">Безопасность</a>
      </div>
      <a class="navCta" href="login.html">Войти</a>
    </nav>

    <section id="top" class="hero section">
      <div class="heroText">
        <div class="eyebrow">🤖 AI copilot для агентств и PPC-команд</div>
        <h1>Автоматизируйте аудит, мониторинг и оптимизацию Яндекс.Директа</h1>
        <p>
          DirectPilot AI подключается к рекламным кабинетам, находит потери бюджета, объясняет рекомендации и
          помогает безопасно внедрять изменения с подтверждением специалиста.
        </p>
        <div class="heroActions">
          <a class="primaryButton" href="login.html">Перейти в кабинет <span>→</span></a>
          <a class="secondaryButton" href="#features">Что умеет сервис</a>
        </div>
        <div class="trustRow">
          <span>✓ Read-only старт</span>
          <span>✓ Approval workflow</span>
          <span>✓ Журнал изменений</span>
        </div>
      </div>

      <div id="demo" class="dashboardCard" aria-label="Демо дашборда DirectPilot AI">
        <div class="cardHeader">
          <div>
            <span class="muted">Клиент</span>
            <strong>${currentClient().name}</strong>
          </div>
          <span class="status"><span></span> AI анализ завершён</span>
        </div>

        <div class="kpiGrid">
          <article class="kpi green"><span>Экономия бюджета</span><strong>18%</strong></article>
          <article class="kpi orange"><span>Аномалии найдены</span><strong>24</strong></article>
          <article class="kpi blue"><span>CPA за 7 дней</span><strong>−12%</strong></article>
        </div>

        <div class="chartPanel">
          <div class="chartTopline">
            <div>
              <span class="muted">CPA / Конверсии</span>
              <strong>Прогноз после рекомендаций</strong>
            </div>
            <span class="chartIcon">↗</span>
          </div>
          <div class="chartBars" aria-hidden="true">
            ${[42, 68, 51, 76, 59, 86, 72].map((height) => `<span style="height: ${height}%"></span>`).join('')}
          </div>
        </div>

        <div class="recommendationList">
          ${recommendations.slice(0, 3).map((item) => `
            <article class="recommendation">
              <div>
                <strong>${item.title}</strong>
                <p>${item.reason}</p>
              </div>
              <span>${item.impact}</span>
            </article>
          `).join('')}
        </div>
      </div>
    </section>

    <section id="features" class="section compact">
      <div class="sectionHeading">
        <span class="eyebrow">⚙️ Основные модули</span>
        <h2>Визуальный каркас будущего SaaS-продукта</h2>
        <p>
          Первая версия интерфейса сфокусирована на ценности для агентств: быстрый аудит, понятные рекомендации,
          контроль KPI и безопасное применение изменений.
        </p>
      </div>
      <div class="featureGrid">
        ${[
          ['⚡', 'AI-аудит аккаунта', 'Проверка структуры, целей Метрики, UTM, ключей, ставок, объявлений и расходов без конверсий.'],
          ['🔔', 'Мониторинг аномалий', 'Сервис предупреждает о резком росте CPA, падении конверсий, перерасходе и проблемах модерации.'],
          ['✨', 'Рекомендации с объяснениями', 'Каждое действие сопровождается причиной, прогнозом эффекта, уровнем риска и списком затронутых объектов.'],
          ['🛡️', 'Безопасный автопилот', 'Dry-run, согласования, лимиты, журнал изменений и откат — ИИ действует только в рамках политик клиента.'],
          ['💬', 'Чат по рекламному аккаунту', 'Можно спросить: «где сливается бюджет?», «почему вырос CPA?» или «что сделать на этой неделе?».'],
          ['📄', 'Отчёты для клиентов', 'Автоматические weekly-отчёты: что изменилось, что сделал специалист и какие гипотезы проверяются.'],
        ].map(([icon, title, text]) => `
          <article class="featureCard">
            <span class="featureIcon">${icon}</span>
            <h3>${title}</h3>
            <p>${text}</p>
          </article>
        `).join('')}
      </div>
    </section>

    <section id="workflow" class="section split">
      <div>
        <span class="eyebrow">🖱️ Workflow</span>
        <h2>От read-only аудита до управляемого автопилота</h2>
        <p>
          Продукт можно запускать поэтапно: сначала дать специалисту прозрачную аналитику, затем добавить
          рекомендации и только после накопления доверия включать автоматические действия в рамках лимитов.
        </p>
      </div>
      <div class="steps">
        ${['Подключите Яндекс.Директ, Метрику и CRM', 'Получите аудит и список потерь бюджета', 'Согласуйте безопасные рекомендации', 'Включите автопилот для низкорисковых действий'].map((step, index) => `
          <article class="step">
            <span>${index + 1}</span>
            <p>${step}</p>
            <strong>›</strong>
          </article>
        `).join('')}
      </div>
    </section>

    <section id="security" class="section security">
      <div class="securityCard">
        <span class="securityIcon">🔐</span>
        <h2>ИИ не меняет рекламу без правил и контроля</h2>
        <p>
          Для каждой рекомендации показывается diff, причина, ожидаемый эффект и риск. Автопилот работает только в
          рамках политики клиента: лимиты бюджета, запрет удаления, подтверждение критичных операций и полный audit log.
        </p>
        <div class="policyGrid">
          <span>🎯 KPI-политики</span>
          <span>₽ Бюджетные лимиты</span>
          <span>📊 Измерение эффекта</span>
        </div>
      </div>
    </section>
  `;
}


function renderLogin() {
  return `
    <section class="authPage">
      <a class="brand authBrand" href="index.html">
        <span class="brandIcon">✦</span>
        DirectPilot AI
      </a>
      <div class="authCard">
        <span class="eyebrow">🔐 Вход по email-коду</span>
        <h1>Войдите в личный кабинет</h1>
        <p>Мы отправим одноразовый код на почту. После подтверждения откроется отдельная страница кабинета.</p>
        <form class="authForm" data-auth-form>
          <div class="authField">
            <label for="login-email">Email</label>
            <input id="login-email" type="email" name="email" value="${escapeHtml(authEmail)}" placeholder="you@agency.ru" autocomplete="email" inputmode="email" autofocus required />
          </div>
          ${authStep === 'code' ? `
            <div class="authField">
              <label for="login-code">Код из письма</label>
              <input id="login-code" type="text" name="code" value="${escapeHtml(authCode)}" inputmode="numeric" maxlength="6" placeholder="000000" autocomplete="one-time-code" required />
            </div>
          ` : ''}
          <button class="primaryButton" type="submit" ${authLoading ? 'disabled' : ''}>${authLoading ? 'Отправляем...' : (authStep === 'code' ? 'Подтвердить код' : 'Получить код')}</button>
        </form>
        ${authStatus ? `<div class="authStatus">${authStatus}</div>` : ''}
        ${devCode ? `<div class="authStatus dev">Dev code: <strong>${devCode}</strong></div>` : ''}
        ${renderBackendApiConfig()}
        <a class="secondaryButton" href="index.html">← На главную</a>
      </div>
    </section>
  `;
}

async function requestEmailCode(email) {
  try {
    const response = await fetch(`${API_BASE}/auth/email/request-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось отправить код');
    return payload;
  } catch (error) {
    throw new Error(`Не удалось подключиться к backend. Проверьте Vercel URL или directpilot_api_base. Текущий API_BASE: ${API_BASE}`);
  }
}

async function verifyEmailCode(email, code) {
  const response = await fetch(`${API_BASE}/auth/email/verify-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, code }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось подтвердить код');
  return payload;
}

async function connectYandexIntegration() {
  const response = await apiFetch('/auth/yandex/start');
  const payload = await response.json();
  if (!response.ok || !payload.auth_url) throw new Error(payload.detail || payload.message || 'OAuth URL не получен');
  window.location.href = payload.auth_url;
}

async function loadAiStatus() {
  try {
    const response = await fetch(`${API_BASE}/ai/openrouter/status`);
    aiStatus = response.ok ? await response.json() : { models: [], configured: false, message: 'Не удалось получить статус OpenRouter.' };
    const hasSavedSettings = Boolean(window.localStorage.getItem(getAiModelSettingsKey()));
    if (!hasSavedSettings) {
      aiPreset = aiStatus.recommended_default_preset || 'economy';
      aiModel = aiStatus.recommended_default_model || aiStatus.default_model || aiStatus.models?.[0]?.id || aiModel;
      saveAiModelSettings();
    }
    if (isCustomAiModel()) aiCustomModel = aiModel;
    if (activeView === 'ai') render();
  } catch (error) {
    aiStatus = { models: [], configured: false, message: 'Backend OpenRouter недоступен.' };
    if (activeView === 'ai') render();
  }
}

async function requestAiInsight() {
  aiLoading = true;
  aiError = '';
  aiResponse = null;
  render();
  try {
    const response = await apiFetch('/ai/openrouter/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...aiRequestOptions(), prompt: aiPrompt }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'OpenRouter не вернул ответ');
    aiResponse = payload;
  } catch (error) {
    aiError = error.message;
  } finally {
    aiLoading = false;
    render();
  }
}

async function testSelectedAiModel() {
  aiModelTestLoading = true;
  aiModelTestStatus = 'Проверяем модель коротким запросом...';
  render();
  try {
    const response = await apiFetch('/ai/openrouter/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...aiRequestOptions(), prompt: 'Ответь одним словом: OK' }),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      const normalized = normalizeAiErrorPayload(payload, 'Модель не ответила на тестовый запрос.');
      if (normalized.code === 'openrouter_rate_limited' || response.status === 429) {
        aiModelTestStatus = `Модель временно ограничена по лимитам: ${normalized.model}. Free/custom модели могут чаще получать rate limit.`;
      } else if (!aiStatus.configured || response.status === 503) {
        aiModelTestStatus = 'OpenRouter не настроен или недоступен на backend.';
      } else {
        aiModelTestStatus = `${normalized.message} Модель: ${normalized.model}.`;
      }
      return;
    }
    aiModelTestStatus = `Модель отвечает. Фактическая модель: ${payload.model || activeAiModel()}.`;
  } catch (error) {
    aiModelTestStatus = `Не удалось проверить модель: ${error.message}`;
  } finally {
    aiModelTestLoading = false;
    render();
  }
}



async function requestAiChatAnswer() {
  if (!selectedClientId) {
    aiChatError = 'Сначала добавьте клиента: чат анализирует данные в контексте выбранного клиента.';
    render();
    return;
  }
  const message = aiChatInput.trim();
  if (!message) return;
  const history = aiChatMessages.slice(-8);
  lastAiAction = { type: 'chat', message };
  aiChatMessages = [...aiChatMessages, { role: 'user', content: message }];
  aiChatInput = '';
  aiChatLoading = true;
  aiChatError = '';
  aiChatErrorDetails = null;
  aiChatToolTraces = [];
  render();
  try {
    const response = await apiFetch('/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: selectedClientId, ...aiRequestOptions(), message, history, client_context: currentClient(), selected_campaign_name: selectedAiCampaignName || null }),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      const normalized = normalizeAiErrorPayload(payload, 'AI-чат не вернул ответ');
      aiChatErrorDetails = normalized;
      throw new Error(normalized.message);
    }
    aiChatMessages = [...aiChatMessages, { role: 'assistant', content: payload.answer, source: payload.source }];
    aiChatToolTraces = payload.tool_traces || [];
  } catch (error) {
    aiChatError = error.message;
  } finally {
    aiChatLoading = false;
    saveActiveAiState();
    render();
  }
}

async function requestClientAiRecommendations() {
  if (!selectedClientId) {
    clientAiError = 'Сначала добавьте клиента и подключите аккаунты Яндекс.Директа/Метрики.';
    render();
    return;
  }
  clientAiLoading = true;
  clientAiError = '';
  clientAiRecommendations = null;
  lastAiAction = { type: 'recommendations' };
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/ai/recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...aiRequestOptions(), client_context: currentClient() }),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      const normalized = normalizeAiErrorPayload(payload, 'Не удалось сформировать AI-рекомендации');
      clientAiError = `${normalized.message} Модель: ${normalized.model}. Free/custom модели могут часто получать rate limit.`;
      throw new Error(clientAiError);
    }
    clientAiRecommendations = payload;
    clientAiRecommendationsByClientId[selectedClientId] = payload;
  } catch (error) {
    clientAiError = clientAiError || error.message;
  } finally {
    clientAiLoading = false;
    render();
  }
}

async function loadIntegrationStatus() {
  try {
    const response = await apiFetch('/auth/yandex/status');
    integrationStatus = response.ok ? await response.json() : {};
    if (activeView === 'integrations') render();
  } catch (error) {
    if (error.message === 'Authentication required') return;
    integrationStatus = { message: 'Не удалось получить статус интеграций' };
    if (activeView === 'integrations') render();
  }
}

async function loadClientYandexIntegration(force = false) {
  if (!selectedClientId || clientYandexLoading) return;
  if (!force && clientYandexLoadedFor === selectedClientId && clientYandexIntegration) return;
  clientYandexLoading = true;
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/integrations/yandex`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить привязку Яндекса');
    clientYandexIntegration = payload;
    clientYandexLoadedFor = selectedClientId;
    clientYandexStatus = payload.message || '';
  } catch (error) {
    if (error.message === 'Authentication required') return;
    clientYandexIntegration = null;
    clientYandexLoadedFor = selectedClientId;
    clientYandexStatus = error.message;
  } finally {
    clientYandexLoading = false;
    if (['dashboard', 'integrations', 'ai', 'optimization'].includes(activeView)) render();
  }
}

async function bindClientYandexAccount(accountId) {
  if (!selectedClientId || !accountId) return;
  clientYandexStatus = 'Привязываем Яндекс-аккаунт...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/integrations/yandex`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yandex_account_id: accountId }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось привязать аккаунт');
    clientYandexStatus = 'Яндекс-аккаунт привязан к клиенту.';
    await loadClientYandexIntegration(true);
    clientsLoaded = false;
    await loadClientsFromApi();
  } catch (error) {
    clientYandexStatus = error.message;
  } finally {
    render();
  }
}

async function unbindClientYandexAccount() {
  if (!selectedClientId) return;
  clientYandexStatus = 'Отвязываем Яндекс-аккаунт...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/integrations/yandex`, { method: 'DELETE' });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось отвязать аккаунт');
    clientYandexStatus = 'Яндекс-аккаунт отвязан от клиента.';
    await loadClientYandexIntegration(true);
    clientsLoaded = false;
    await loadClientsFromApi();
  } catch (error) {
    clientYandexStatus = error.message;
  } finally {
    render();
  }
}



async function runClientSync() {
  if (!selectedClientId) return;
  syncLoading = true;
  syncStatusMessage = 'Запускаем синхронизацию...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/sync`, { method: 'POST' });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Ошибка синхронизации');
    if (payload.rows_loaded === 0 && (payload.status === 'failed' || payload.status === 'no_data' || payload.status === 'success')) {
      syncStatusMessage = payload.error || 'Данные не загружены: подключите Яндекс.Директ или проверьте выбранный период.';
    } else {
      syncStatusMessage = `Синхронизация: ${payload.status}, загружено кампаний: ${payload.rows_loaded}, тип отчёта: ${payload.source_type}`;
    }
    clientsLoaded = false;
    await loadClientsFromApi();
    await loadPerformanceSummary();
    await loadSyncJobs();
    optimizationPlan = null;
    optimizationPlanByClientId[selectedClientId] = null;
    await loadOptimizationPlan();
  } catch (error) {
    syncStatusMessage = `Ошибка синхронизации: ${error.message}`;
    await loadSyncJobs();
  } finally {
    syncLoading = false;
    render();
  }
}

async function loadPerformanceSummary() {
  if (!selectedClientId) return;
  perfLoading = true;
  perfSummary = null;
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/performance-summary`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить сводку');
    perfSummary = payload;
  } catch (error) {
    syncStatusMessage = `Ошибка сводки: ${error.message}`;
  } finally {
    perfLoading = false;
    render();
  }
}

function resetSelectedClientOperationalState() {
  perfSummary = null;
  syncJobs = [];
  syncJobsStatus = '';
  syncStatusMessage = '';
  clientYandexIntegration = null;
  clientYandexLoadedFor = '';
  clientYandexStatus = '';
  optimizationPlan = optimizationPlanByClientId[selectedClientId] || null;
  optimizationPlanStatus = '';
  optimizationFilter = 'all';
  optimizationActions = optimizationActionsByClientId[selectedClientId] || [];
  optimizationActionFilter = optimizationActionFilterByClientId[selectedClientId] || 'all';
  optimizationActionsStatus = '';
  optimizationExecutionPreviewStatus = '';
  optimizationActionsLoadedFor = optimizationActionsByClientId[selectedClientId] ? selectedClientId : '';
  businessContext = null;
  businessContextStatus = '';
  businessContextLoadedFor = '';
}

async function loadBusinessContext(force = false) {
  if (!selectedClientId || businessContextLoading) return;
  if (!force && businessContextLoadedFor === selectedClientId && businessContext) return;
  businessContextLoading = true;
  businessContextStatus = 'Загружаем контекст бизнеса...';
  if (['business-context', 'ai', 'dashboard'].includes(activeView)) render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/business-context`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить контекст бизнеса');
    businessContext = payload;
    businessContextLoadedFor = selectedClientId;
    businessContextStatus = '';
  } catch (error) {
    businessContextStatus = `Ошибка контекста бизнеса: ${error.message}`;
    businessContextLoadedFor = selectedClientId;
  } finally {
    businessContextLoading = false;
    if (['business-context', 'ai', 'dashboard'].includes(activeView)) render();
  }
}

async function saveBusinessContextFromForm(form) {
  if (!selectedClientId || !form) return;
  const formData = new FormData(form);
  const fieldNames = [
    'brandName',
    'businessNiche',
    'productSummary',
    'targetAudience',
    'geography',
    'seasonality',
    'mainOffers',
    'conversionActions',
    'averageOrderValue',
    'leadValueNotes',
    'businessConstraints',
    'negativeTopics',
    'landingPageNotes',
    'competitorNotes',
    'manualNotes',
    'memoryNotes',
    'sourceNotes',
  ];
  const payload = {};
  fieldNames.forEach((name) => {
    payload[name] = String(formData.get(name) || '').trim() || null;
  });
  businessContextLoading = true;
  businessContextStatus = 'Сохраняем контекст бизнеса...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/business-context`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    const saved = await response.json();
    if (!response.ok) throw new Error(saved.detail || 'Не удалось сохранить контекст бизнеса');
    businessContext = saved;
    businessContextLoadedFor = selectedClientId;
    businessContextStatus = 'Контекст бизнеса сохранён.';
    await loadPerformanceSummary();
  } catch (error) {
    businessContextStatus = `Ошибка сохранения контекста: ${error.message}`;
  } finally {
    businessContextLoading = false;
    render();
  }
}

async function saveAiMessageToProjectMemory(message) {
  if (!selectedClientId || !message) return;
  businessContextStatus = 'Сохраняем в память проекта...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/business-context/memory-note`, {
      method: 'POST',
      body: JSON.stringify({ note: message }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить в память проекта');
    businessContext = payload;
    businessContextLoadedFor = selectedClientId;
    businessContextStatus = 'Ответ сохранён в память проекта.';
  } catch (error) {
    businessContextStatus = `Ошибка памяти проекта: ${error.message}`;
  } finally {
    render();
  }
}

async function loadSyncJobs() {
  if (!selectedClientId) return;
  syncJobsLoading = true;
  syncJobsStatus = 'Загружаем историю синхронизаций...';
  if (activeView === 'dashboard') render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/sync/jobs`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить историю синхронизаций');
    syncJobs = Array.isArray(payload) ? payload : [];
    syncJobsStatus = syncJobs.length ? `Загружено заданий: ${syncJobs.length}` : 'Синхронизация ещё не запускалась';
  } catch (error) {
    syncJobsStatus = error.message;
  } finally {
    syncJobsLoading = false;
    if (activeView === 'dashboard') render();
  }
}

async function loadOptimizationPlan() {
  if (!selectedClientId) return;
  optimizationPlanLoading = true;
  optimizationPlanStatus = 'Формируем план оптимизации...';
  if (activeView === 'optimization') render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/optimization-plan`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить план оптимизации');
    optimizationPlan = payload;
    optimizationPlanByClientId[selectedClientId] = payload;
    optimizationPlanStatus = payload.actions?.length ? `Черновиков действий: ${payload.actions.length}` : 'Критичных действий не найдено.';
  } catch (error) {
    optimizationPlanStatus = error.message;
  } finally {
    optimizationPlanLoading = false;
    if (activeView === 'optimization') render();
  }
}

async function loadOptimizationActions() {
  if (!selectedClientId) return;
  optimizationActionsLoading = true;
  optimizationActionsStatus = 'Загружаем черновики согласования...';
  if (activeView === 'optimization') render();
  try {
    const query = optimizationActionFilter && optimizationActionFilter !== 'all' ? `?status=${encodeURIComponent(optimizationActionFilter)}` : '';
    const response = await apiFetch(`/clients/${selectedClientId}/optimization-actions${query}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить черновики согласования');
    optimizationActions = Array.isArray(payload.actions) ? payload.actions : [];
    optimizationActionsByClientId[selectedClientId] = optimizationActions;
    optimizationActionsLoadedFor = selectedClientId;
    optimizationActionsStatus = optimizationActions.length ? `Сохранено черновиков: ${optimizationActions.length}` : 'Сохранённых черновиков пока нет.';
  } catch (error) {
    optimizationActionsStatus = error.message;
  } finally {
    optimizationActionsLoading = false;
    if (activeView === 'optimization') render();
  }
}

async function saveOptimizationPlanAsDrafts() {
  if (!selectedClientId) return;
  optimizationActionsLoading = true;
  optimizationActionsStatus = 'Сохраняем текущий план как черновики...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/optimization-actions/from-plan`, { method: 'POST' });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить черновики');
    optimizationActions = Array.isArray(payload.actions) ? payload.actions : [];
    optimizationActionsByClientId[selectedClientId] = optimizationActions;
    optimizationActionsStatus = optimizationActions.length ? `Черновики сохранены: ${optimizationActions.length}` : 'В плане нет действий для сохранения.';
    await loadOptimizationActions();
  } catch (error) {
    optimizationActionsStatus = error.message;
  } finally {
    optimizationActionsLoading = false;
    render();
  }
}

async function updateOptimizationAction(actionId, statusValue, commentValue) {
  if (!selectedClientId || !actionId) return;
  optimizationActionsStatus = 'Обновляем статус черновика...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/optimization-actions/${actionId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: statusValue, user_comment: commentValue || null }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось обновить черновик');
    optimizationActions = optimizationActions.map((item) => (item.id === payload.id ? payload : item));
    optimizationActionsByClientId[selectedClientId] = optimizationActions;
    optimizationActionsStatus = `Статус обновлён: ${optimizationStatusLabel(payload.status)}.`;
  } catch (error) {
    optimizationActionsStatus = error.message;
  } finally {
    render();
  }
}

async function loadOptimizationExecutionPreview(actionId) {
  if (!selectedClientId || !actionId) return;
  optimizationExecutionPreviewStatus = 'Загружаем безопасный предпросмотр...';
  render();
  try {
    const response = await apiFetch(`/clients/${selectedClientId}/optimization-actions/${actionId}/execution-preview`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить предпросмотр применения');
    optimizationExecutionPreviewsByActionId[actionId] = payload;
    optimizationExecutionPreviewStatus = 'Предпросмотр загружен. Изменения в Яндекс.Директ не применялись.';
  } catch (error) {
    optimizationExecutionPreviewStatus = error.message;
  } finally {
    render();
  }
}

function renderClientContextStrip() {
  const client = currentClient();
  const hasClient = Boolean(client.id);
  const goals = perfSummary?.selectedGoalIds?.join(', ') || client.conversionGoalIds || client.mainGoalId || '';
  const yandexStatus = clientYandexLoading
    ? { status: 'loading', value: 'Загрузка' }
    : clientYandexIntegration?.connected
      ? { status: 'ready', value: 'Готово' }
      : { status: hasClient ? 'action_needed' : 'pending', value: hasClient ? 'Нужно действие' : 'Нет данных' };
  const syncStatus = syncLoading
    ? { status: 'loading', value: 'Загрузка' }
    : client.syncStatus === 'ok'
      ? { status: 'ready', value: 'Готово' }
      : client.syncStatus === 'error'
        ? { status: 'error', value: 'Ошибка' }
        : { status: hasClient ? 'pending' : 'blocked', value: hasClient ? 'Нет данных' : 'Блокер' };
  const items = [
    { label: 'Клиент', value: hasClient ? client.name : 'Не выбран', status: hasClient ? 'ready' : 'action_needed' },
    { label: 'Direct', value: hasClientValue(client.directLogin) ? client.directLogin : 'Нужно действие', status: hasClientValue(client.directLogin) ? 'ready' : 'action_needed' },
    { label: 'Метрика', value: hasClientValue(client.metricaCounter) ? client.metricaCounter : 'Нужно действие', status: hasClientValue(client.metricaCounter) ? 'ready' : 'action_needed' },
    { label: 'Цели', value: goals || 'Нет данных', status: goals ? 'ready' : 'pending' },
    { label: 'Яндекс', value: yandexStatus.value, status: yandexStatus.status },
    { label: 'Sync', value: syncStatus.value, status: syncStatus.status },
  ];
  return `
    <section class="panel clientSourcePanel">
      ${items.map((item) => `
        <div>
          <span class="muted">${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
          <small>${escapeHtml(compactStatusLabel(item.status))}</small>
        </div>
      `).join('')}
    </section>
  `;
}

function renderShell(content) {
  const client = currentClient();
  return `
    <div class="appShell">
      <aside class="sidebar">
        <a class="brand appBrand" href="index.html">
          <span class="brandIcon">✦</span>
          <span>DirectPilot AI</span>
        </a>
        <nav class="sideNav" aria-label="Навигация личного кабинета">
          ${navItems.map((item) => `
            <button class="sideNavItem ${activeView === item.id ? 'active' : ''}" data-view="${item.id}">
              <span>${item.icon}</span>${item.label}
            </button>
          `).join('')}
        </nav>
        <div class="sidebarNote">
          <strong>Рабочий кабинет</strong>
          <p>${escapeHtml(currentEmail || 'Сессия не найдена')}</p>
          <button class="secondaryButton" type="button" data-logout>Выйти</button>
        </div>
      </aside>

      <section class="workspace">
        <header class="appHeader">
          <div>
            <span class="muted">Выбранный клиент</span>
            <h1>${client.name}</h1>
          </div>
          <label class="clientSelect">
            <span>Клиент</span>
            <select data-client-select>
              ${accountClients.length ? accountClients.map((item) => `<option value="${item.id}" ${item.id === selectedClientId ? 'selected' : ''}>${item.name}</option>`).join('') : '<option value="">Добавьте клиента</option>'}
            </select>
            <small>Direct: ${client.directLogin} · Метрика: ${client.metricaCounter}</small>
          </label>
        </header>
        ${renderClientContextStrip()}
        ${content}
      </section>
    </div>
  `;
}

function readinessIcon(status) {
  return { ready: '✅', action_needed: '⚠️', blocked: '⛔', pending: '⏳' }[status] || '⏳';
}

function readinessLabel(status) {
  return { ready: 'Готово', action_needed: 'Нужно действие', blocked: 'Блокер', pending: 'Ожидает' }[status] || 'Ожидает';
}

function renderReadinessPanel(readiness, nextAction) {
  const client = getSelectedClient();
  const readyCount = readiness.filter((item) => item.status === 'ready').length;
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Готовность MVP</h3>
          <p>${client.id ? escapeHtml(client.name) : 'Создайте клиента, чтобы подключить данные и запустить анализ.'}</p>
        </div>
        <span class="aiStatusBadge ${readyCount === readiness.length ? 'ready' : 'pending'}">${formatNumberSafe(readyCount)} из ${formatNumberSafe(readiness.length)}</span>
      </div>
      <div class="featureGrid">
        ${readiness.map((item) => `
          <article class="featureCard">
            <span class="featureIcon">${readinessIcon(item.status)}</span>
            <h3>${escapeHtml(item.label)}</h3>
            <p>${escapeHtml(item.description)}</p>
            <small>${readinessLabel(item.status)} · ${escapeHtml(item.nextAction)}</small>
          </article>
        `).join('')}
      </div>
      <div class="heroActions">
        <button class="secondaryButton" data-go-view="clients">Клиенты</button>
        <button class="secondaryButton" data-go-view="integrations">Интеграции</button>
        <button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
        <button class="approveButton" data-go-view="ai">AI-аналитик</button>
      </div>
    </section>
  `;
}

function renderSyncCenter() {
  const client = getSelectedClient();
  const lastJob = syncJobs[0];
  const yandexBound = Boolean(clientYandexIntegration?.connected);
  const directReady = hasClientValue(client.directLogin);
  const helper = !yandexBound
    ? 'Сначала привяжите Яндекс-аккаунт к этому клиенту.'
    : !directReady
      ? 'Укажите логин Яндекс.Директа в настройках клиента.'
      : 'Можно запускать синхронизацию. Backend загрузит сохранённые данные Яндекс.Директа.';

  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Синхронизация данных</h3>
          <p>${escapeHtml(client.name)} · ${escapeHtml(helper)}</p>
        </div>
        <span class="aiStatusBadge ${client.syncStatus === 'ok' ? 'ready' : 'pending'}">${escapeHtml(formatSyncStatus(client.syncStatus))}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi blue"><span>Яндекс</span><strong>${yandexBound ? 'Привязан' : 'Не привязан'}</strong></article>
        <article class="kpi green"><span>Версия sync</span><strong>${formatNumberSafe(client.syncVersion || 0)}</strong></article>
        <article class="kpi orange"><span>Последний sync</span><strong>${escapeHtml(formatDateSafe(client.lastSyncedAt))}</strong></article>
      </div>
      ${client.syncError ? `<div class="authStatus aiError">${escapeHtml(client.syncError)}</div>` : ''}
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
      <div class="heroActions">
        <button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
        <button class="secondaryButton" data-load-summary ${perfLoading ? 'disabled' : ''}>${perfLoading ? 'Загружаем...' : 'Обновить сводку'}</button>
        <button class="secondaryButton" data-load-sync-jobs ${syncJobsLoading ? 'disabled' : ''}>История синхронизаций</button>
      </div>
      <div class="authStatus integrationStatus">${escapeHtml(syncJobsStatus || (lastJob ? `Последнее задание: ${lastJob.status}, загружено кампаний: ${lastJob.rows_loaded}` : 'Синхронизация ещё не запускалась'))}</div>
      ${lastJob ? `<p>Последний результат: ${escapeHtml(lastJob.status)} · загружено кампаний: ${formatNumberSafe(lastJob.rows_loaded)} · ${escapeHtml(lastJob.source_type)}${lastJob.error ? ` · ${escapeHtml(lastJob.error)}` : ''}</p>` : ''}
      ${syncJobs.length ? `
        <div class="tableWrap">
          <table>
            <thead><tr><th>Статус</th><th>Загружено кампаний</th><th>Тип отчёта</th><th>Период</th><th>Завершено</th><th>Ошибка</th></tr></thead>
            <tbody>${syncJobs.slice(0, 5).map((job) => `
              <tr>
                <td><span class="tableStatus">${escapeHtml(job.status)}</span></td>
                <td>${formatNumberSafe(job.rows_loaded)}</td>
                <td>${escapeHtml(job.source_type)}</td>
                <td>${escapeHtml(formatDateSafe(job.period_from))} — ${escapeHtml(formatDateSafe(job.period_to))}</td>
                <td>${escapeHtml(formatDateSafe(job.finished_at || job.started_at || job.created_at))}</td>
                <td>${escapeHtml(job.error || '—')}</td>
              </tr>
            `).join('')}</tbody>
          </table>
        </div>
      ` : ''}
    </section>
  `;
}

function renderSyncDiagnosticsPanel(compact = false) {
  const client = getSelectedClient();
  const diagnostics = perfSummary?.syncDiagnostics || {};
  const warnings = diagnostics.warnings || perfSummary?.goalDataWarnings || [];
  const goalIds = diagnostics.selectedGoalIds?.length
    ? diagnostics.selectedGoalIds
    : (perfSummary?.selectedGoalIds || String(client.conversionGoalIds || client.mainGoalId || '').split(/[,\s]+/).filter(Boolean));
  const hasDiagnostics = Boolean(perfSummary);
  const level = diagnostics.dataQualityLevel || (hasDiagnostics ? 'warning' : 'pending');
  const levelLabel = {
    ok: 'Готово',
    warning: 'Нужно действие',
    critical: 'Блокер',
    pending: 'Нет данных',
  }[level] || 'Нет данных';
  const goalDataMissingMessage = 'Директ не вернул данные по выбранным целям. Проверьте ID целей и запустите синхронизацию повторно.';
  const message = diagnostics.hasGoalIds && !diagnostics.hasGoalData
    ? goalDataMissingMessage
    : (diagnostics.message || (
      hasDiagnostics
        ? (perfSummary?.hasGoalData ? 'Данные по выбранным целям Директа загружены.' : 'Проверьте цели, конверсии и синхронизацию.')
        : 'Сводка ещё не загружена. Запустите синхронизацию или обновите сводку, чтобы увидеть качество данных.'
    ));
  const nextAction = !client.id
    ? { text: 'Создайте клиента', view: 'clients' }
    : !clientYandexIntegration?.connected
      ? { text: 'Привяжите Яндекс', view: 'integrations' }
      : !hasDiagnostics || !diagnostics.directRowsLoaded
        ? { text: 'Запустите синхронизацию', action: 'sync' }
        : !goalIds.length
          ? { text: 'Укажите цели Метрики', view: 'clients' }
          : diagnostics.hasGoalIds && !diagnostics.hasGoalData
            ? { text: 'Проверьте цели в отчёте Директа', view: 'clients' }
            : { text: 'Открыть AI-анализ', view: 'ai' };
  return `
    <section class="panel ${compact ? 'compact' : ''}">
      <div class="panelHeader">
        <div>
          <h3>Диагностика синхронизации</h3>
          <p>${escapeHtml(message)}</p>
        </div>
        <span class="aiStatusBadge ${level === 'ok' ? 'ready' : 'pending'}">${escapeHtml(levelLabel)}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi blue"><span>Загружено кампаний</span><strong>${formatNumberSafe(diagnostics.directRowsLoaded || 0)}</strong></article>
        <article class="kpi green"><span>Цели</span><strong>${escapeHtml(goalIds.join(', ') || 'не указаны')}</strong></article>
        <article class="kpi orange"><span>Конверсии по целям</span><strong>${formatNumberSafe(diagnostics.goalConversionsTotal || perfSummary?.goalConversionsTotal || 0)}</strong></article>
      </div>
      ${warnings.length ? `<div class="authStatus aiError">${warnings.map((item) => `<p>${escapeHtml(humanizeDataWarning(item))}</p>`).join('')}</div>` : ''}
      <div class="heroActions">
        ${nextAction.action === 'sync'
          ? `<button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${escapeHtml(nextAction.text)}</button>`
          : `<button class="secondaryButton" data-go-view="${escapeHtml(nextAction.view)}">${escapeHtml(nextAction.text)}</button>`}
        <button class="secondaryButton" data-load-summary ${perfLoading ? 'disabled' : ''}>Обновить сводку</button>
      </div>
    </section>
  `;
}

function renderYesterdaySummaryPanel() {
  const summary = perfSummary?.yesterdayCampaignSummary || {};
  const totals = summary.totals || {};
  const campaigns = summary.campaigns || [];
  const recommendations = summary.recommendations || [];
  if (!summary.hasData) {
    return `
      <section class="panel emptyStatePanel compact">
        <div class="panelHeader">
          <div>
            <h3>Сводка за вчера</h3>
            <p>${escapeHtml(summary.message || 'Данные за вчера ещё не загружены. Запустите синхронизацию.')}</p>
          </div>
          <span class="aiStatusBadge pending">Нет данных</span>
        </div>
        <div class="heroActions">
          <button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
          <button class="secondaryButton" data-load-summary ${perfLoading ? 'disabled' : ''}>Обновить сводку</button>
        </div>
      </section>
    `;
  }
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Сводка за вчера</h3>
          <p>${escapeHtml(summary.date || '')} · Кампании за один день, без выводов о тренде. Основная метрика — конверсии по выбранным целям.</p>
        </div>
        <span class="aiStatusBadge ready">Загружено кампаний: ${formatNumberSafe(campaigns.length)}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Расход</span><strong>${formatMoneySafe(totals.cost)}</strong></article>
        <article class="kpi blue"><span>Показы</span><strong>${formatNumberSafe(totals.impressions)}</strong></article>
        <article class="kpi orange"><span>Клики</span><strong>${formatNumberSafe(totals.clicks)}</strong></article>
        <article class="kpi green"><span>Конверсии по целям</span><strong>${formatNumberSafe(totals.goalConversions)}</strong></article>
        <article class="kpi blue"><span>CPA по целям</span><strong>${totals.goalCpa == null ? '—' : formatMoneySafe(totals.goalCpa)}</strong></article>
        <article class="kpi orange"><span>CR</span><strong>${totals.conversionRate == null ? '—' : formatPercentSafe(totals.conversionRate)}</strong></article>
      </div>
      <p>CTR: ${formatPercentSafe(totals.ctr)} · CPC: ${formatMoneySafe(totals.avgCpc)} · Цели: ${escapeHtml(perfSummary?.selectedGoalIds?.join(', ') || currentClient().conversionGoalIds || currentClient().mainGoalId || '—')}</p>
      ${campaigns.length ? `
        <div class="tableWrap">
          <table>
            <thead><tr><th>Кампания</th><th>Расход</th><th>Клики</th><th>CTR</th><th>Конверсии по целям</th><th>CPA по целям</th><th>Сигналы</th></tr></thead>
            <tbody>${campaigns.slice(0, 10).map((campaign) => `
              <tr>
                <td>${escapeHtml(campaign.campaignName || '—')}</td>
                <td>${formatMoneySafe(campaign.cost)}</td>
                <td>${formatNumberSafe(campaign.clicks)}</td>
                <td>${formatPercentSafe(campaign.ctr)}</td>
                <td>${campaign.goalConversions == null ? '—' : formatNumberSafe(campaign.goalConversions)}</td>
                <td>${campaign.goalCpa == null ? '—' : formatMoneySafe(campaign.goalCpa)}</td>
                <td>${escapeHtml(renderIssueFlags(campaign.issueFlags || []))}</td>
              </tr>
            `).join('')}</tbody>
          </table>
        </div>
      ` : ''}
      ${recommendations.length ? `
        <div class="featureGrid">
          ${recommendations.slice(0, 4).map((item) => `
            <article class="featureCard">
              <span class="featureIcon">!</span>
              <h3>Что посмотреть</h3>
              <p>${escapeHtml(item)}</p>
            </article>
          `).join('')}
        </div>
      ` : ''}
    </section>
  `;
}

function renderPerformanceSummaryPanel() {
  if (!perfSummary) {
    return `
      <section class="panel emptyStatePanel compact">
        <h3>Сводка эффективности не загружена</h3>
        <p>Нет сохранённых данных Яндекс.Директа. Запустите синхронизацию, чтобы AI увидел кампании, расходы и конверсии.</p>
        <div class="heroActions">
          <button class="secondaryButton" data-go-view="integrations">Проверить интеграции</button>
          <button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
        </div>
        <button class="approveButton" data-load-summary ${perfLoading ? 'disabled' : ''}>${perfLoading ? 'Загружаем...' : 'Показать сводку'}</button>
      </section>
    `;
  }

  const totals = perfSummary.totals || {};
  const campaigns = perfSummary.campaigns || [];
  const issueCount = campaigns.reduce((sum, item) => sum + (item.issue_flags?.length || 0), 0);
  const selectedGoalIds = perfSummary.selectedGoalIds?.length ? perfSummary.selectedGoalIds : [perfSummary.selectedGoalId].filter(Boolean);
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Сводка эффективности</h3>
          <p>${campaigns.length ? `Кампаний: ${campaigns.length}, флагов: ${issueCount}. ${perfSummary.hasGoalData ? 'Данные по выбранным целям Директа загружены.' : 'Данные по выбранным целям недоступны, проверьте цели и синхронизацию.'}` : 'Нет сохранённых данных Яндекс.Директа. Запустите синхронизацию после подключения Яндекса.'}</p>
        </div>
        <span class="aiStatusBadge ${campaigns.length ? 'ready' : 'pending'}">${escapeHtml(perfSummary.message)}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Расход</span><strong>${formatMoneySafe(totals.cost)}</strong></article>
        <article class="kpi blue"><span>Показы</span><strong>${formatNumberSafe(totals.impressions)}</strong></article>
        <article class="kpi orange"><span>Клики</span><strong>${formatNumberSafe(totals.clicks)}</strong></article>
        <article class="kpi green"><span>Конверсии по целям</span><strong>${perfSummary.goalConversionsTotal == null ? '—' : formatNumberSafe(perfSummary.goalConversionsTotal)}</strong></article>
        <article class="kpi blue"><span>CPA по целям</span><strong>${totals.cpa == null ? '—' : formatMoneySafe(totals.cpa)}</strong></article>
      </div>
      <p>Цели: ${escapeHtml(selectedGoalIds.join(', ') || 'не указаны')} · Данные по выбранным целям Директа · Конверсии по целям: ${perfSummary.goalConversionsTotal == null ? '—' : formatNumberSafe(perfSummary.goalConversionsTotal)}</p>
      <p>Средний CPC: ${formatMoneySafe(totals.avg_cpc)} · CPA по целям: ${totals.cpa == null ? '—' : formatMoneySafe(totals.cpa)} · CTR: ${formatPercentSafe(totals.clicks && totals.impressions ? (totals.clicks / totals.impressions) * 100 : 0)}</p>
      ${campaigns.length ? `
        <div class="tableWrap">
          <table>
            <thead><tr><th>Кампания</th><th>Цели</th><th>Расход</th><th>Показы</th><th>Клики</th><th>Конверсии по целям</th><th>CPA по целям</th><th>Флаги</th></tr></thead>
            <tbody>${campaigns.map((campaign) => `
              <tr>
                <td>${escapeHtml(campaign.campaign_name)}</td>
                <td>${escapeHtml(campaign.goal_ids || selectedGoalIds.join(', ') || '—')}</td>
                <td>${formatMoneySafe(campaign.cost)}</td>
                <td>${formatNumberSafe(campaign.impressions)}</td>
                <td>${formatNumberSafe(campaign.clicks)}</td>
                <td>${campaign.goal_conversions == null ? '—' : formatNumberSafe(campaign.goal_conversions)}</td>
                <td>${campaign.cpa_used == null ? '—' : formatMoneySafe(campaign.cpa_used)}</td>
                <td>${escapeHtml(renderIssueFlags(campaign.issue_flags))}</td>
              </tr>
            `).join('')}</tbody>
          </table>
        </div>
      ` : ''}
    </section>
  `;
}

function negativeKeywordDraftsText(insights) {
  const candidates = (insights?.insights || []).filter((item) => item.recommendedNegativeKeyword);
  return candidates.map((item) => [
    `Минус-слово: ${item.recommendedNegativeKeyword}`,
    `Запрос: ${item.query}`,
    `Кампания: ${item.campaign || '—'}`,
    `Группа: ${item.adGroup || '—'}`,
    `Причина: ${item.reason || 'расход без конверсий'}`,
    'Статус: черновик, изменения в Яндекс.Директ не применялись.',
  ].join('\n')).join('\n\n');
}

function renderSearchQueryInsightsPanel() {
  const insights = perfSummary?.searchQueryInsights || {};
  const items = insights.insights || [];
  const candidates = items.filter((item) => item.recommendedNegativeKeyword);
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <span class="eyebrow">Этап 1.5</span>
          <h3>Поисковые запросы и минус-слова</h3>
          <p>Read-only анализ запросов. Минус-слова показаны только как черновики для ручной проверки и approval.</p>
        </div>
        <span class="aiStatusBadge ${candidates.length ? 'pending' : 'ready'}">${formatNumberSafe(candidates.length)} кандидатов</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi blue"><span>Загружено поисковых запросов</span><strong>${formatNumberSafe(insights.totalQueries || 0)}</strong></article>
        <article class="kpi orange"><span>Кандидаты в минус-слова</span><strong>${formatNumberSafe(insights.candidateNegativeKeywords || 0)}</strong></article>
        <article class="kpi green"><span>Расход без конверсий</span><strong>${formatMoneySafe(insights.totalWasteCost || 0)}</strong></article>
      </div>
      <div class="heroActions">
        <button class="secondaryButton" type="button" data-copy-text="${escapeHtml(negativeKeywordDraftsText(insights))}" ${candidates.length ? '' : 'disabled'}>Скопировать все черновики минус-слов</button>
      </div>
      ${items.length ? `
        <div class="tableWrap">
          <table>
            <thead><tr><th>Запрос</th><th>Кампания</th><th>Группа</th><th>Расход</th><th>Клики</th><th>Конверсии по целям</th><th>Минус-слово</th><th>Уверенность</th><th>Действие</th></tr></thead>
            <tbody>${items.slice(0, 12).map((item) => `
              <tr>
                <td>${escapeHtml(item.query || '—')}</td>
                <td>${escapeHtml(item.campaign || '—')}</td>
                <td>${escapeHtml(item.adGroup || '—')}</td>
                <td>${formatMoneySafe(item.cost)}</td>
                <td>${formatNumberSafe(item.clicks)}</td>
                <td>${item.goalConversions == null ? '—' : formatNumberSafe(item.goalConversions)}</td>
                <td>${escapeHtml(item.recommendedNegativeKeyword || '—')}</td>
                <td>${escapeHtml(item.confidence || 'low')}</td>
                <td><button class="secondaryButton" type="button" data-copy-text="${escapeHtml(`Минус-слово: ${item.recommendedNegativeKeyword || ''}\nЗапрос: ${item.query || ''}\nКампания: ${item.campaign || ''}\nПричина: ${item.reason || ''}\nЧерновик, не применялось в Яндекс.Директ.`)}" ${item.recommendedNegativeKeyword ? '' : 'disabled'}>Скопировать</button></td>
              </tr>
            `).join('')}</tbody>
          </table>
        </div>
      ` : `<div class="emptyStatePanel compact"><h3>Нет данных по поисковым запросам</h3><p>Запустите синхронизацию. Если отчёт поисковых запросов недоступен, синхронизация кампаний всё равно останется рабочей.</p><button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button></div>`}
      <p><strong>Важно:</strong> запросы с конверсиями не предлагаются к минусовке. Черновики не применяются автоматически.</p>
    </section>
  `;
}

function renderYandexDirectAuditPanel(compact = false) {
  const audit = perfSummary?.yandexDirectAudit || {};
  const categories = audit.categories || [];
  const criticalIssues = audit.criticalIssues || [];
  const quickWins = audit.quickWins || [];
  const limitations = audit.limitations || [];
  if (!perfSummary || !audit.grade) {
    return `
      <section class="panel emptyStatePanel compact">
        <h3>AI-аудит Яндекс.Директа</h3>
        <p>Аудит появится после загрузки сводки эффективности. DirectPilot использует только доступные read-only данные и помечает недоступные проверки как «нужны дополнительные данные».</p>
        <div class="heroActions">
          <button class="secondaryButton" data-load-summary ${perfLoading ? 'disabled' : ''}>Обновить сводку</button>
          <button class="approveButton" data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
        </div>
      </section>
    `;
  }
  const shownCategories = compact ? categories.slice(0, 3) : categories;
  return `
    <section class="panel ${compact ? 'compact' : ''}">
      <div class="panelHeader">
        <div>
          <h3>AI-аудит Яндекс.Директа</h3>
          <p>${escapeHtml(audit.summary || 'Профессиональный read-only аудит по чеклисту DirectPilot.')}</p>
          <p>Методология содержит ${formatNumberSafe(audit.frameworkChecksTotal || 55)} проверок. Сейчас DirectPilot автоматически применяет ${formatNumberSafe(audit.implementedChecks || 0)} проверок, по которым есть данные в кабинете. Остальные пункты помечаются как требующие дополнительных данных.</p>
        </div>
        <span class="aiStatusBadge ${Number(audit.score || 0) >= 75 ? 'ready' : 'pending'}">${formatNumberSafe(audit.score || 0)} / 100 · ${escapeHtml(audit.grade || '—')}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Грейд</span><strong>${escapeHtml(audit.grade || '—')}</strong></article>
        <article class="kpi blue"><span>Оценка</span><strong>${formatNumberSafe(audit.score || 0)} / 100</strong></article>
        <article class="kpi orange"><span>Критические проблемы</span><strong>${formatNumberSafe(criticalIssues.length)}</strong></article>
        <article class="kpi green"><span>Быстрые улучшения</span><strong>${formatNumberSafe(quickWins.length)}</strong></article>
      </div>
      ${shownCategories.length ? `
        <div class="featureGrid">
          ${shownCategories.map((category) => `
            <article class="featureCard">
              <span class="featureIcon">${category.grade === 'A' || category.grade === 'B' ? '✅' : category.grade === 'N/A' ? '⏳' : '⚠️'}</span>
              <h3>${escapeHtml(category.title)}</h3>
              <p>Вес: ${formatNumberSafe(category.weight)} · Балл: ${formatNumberSafe(category.score)} · Грейд: ${escapeHtml(auditGradeLabel(category.grade))}</p>
              <small>${formatNumberSafe((category.checks || []).filter((item) => item.status === 'fail').length)} ${auditStatusLabel('fail')} · ${formatNumberSafe((category.checks || []).filter((item) => item.status === 'warning').length)} ${auditStatusLabel('warning')} · ${formatNumberSafe((category.checks || []).filter((item) => item.status === 'na').length)} ${auditStatusLabel('na')}</small>
            </article>
          `).join('')}
        </div>
      ` : ''}
      ${criticalIssues.length ? `
        <div class="authStatus aiError">
          <strong>Критические проблемы</strong>
          <p>Критические проблемы — то, что может искажать аналитику или сливать бюджет.</p>
          ${criticalIssues.slice(0, compact ? 3 : 6).map((item) => `<p>${escapeHtml(item.id)} · ${escapeHtml(item.title)}: ${escapeHtml(item.evidence)}</p>`).join('')}
        </div>
      ` : ''}
      ${quickWins.length ? `
        <div class="authStatus integrationStatus">
          <strong>Быстрые улучшения</strong>
          <p>Быстрые улучшения — задачи, которые можно проверить и исправить без глубокой перестройки кампаний.</p>
          ${quickWins.slice(0, compact ? 3 : 6).map((item) => `<p>${escapeHtml(item.id)} · ${escapeHtml(item.recommendation)}</p>`).join('')}
        </div>
      ` : ''}
      ${!compact && limitations.length ? `
        <details>
          <summary class="secondaryButton">Что пока нельзя проверить автоматически</summary>
          <p>Эти пункты не считаются проваленными: для них нужны дополнительные данные, например посадочные страницы, объявления, расширения, настройки аккаунта или динамика по неделям.</p>
          ${limitations.map((item) => `<p>${escapeHtml(item.id)} · ${escapeHtml(item.title)}: ${escapeHtml(item.evidence)} (${escapeHtml(item.sourceLabel || auditSourceLabel(item.source))})</p>`).join('')}
        </details>
      ` : ''}
      ${!compact ? `
        <div class="heroActions">
          <button class="secondaryButton" type="button" data-ai-quick-action="Разобрать аудит Яндекс.Директа">Разобрать аудит Яндекс.Директа</button>
          <button class="secondaryButton" type="button" data-ai-quick-action="Покажи быстрые улучшения по аудиту Яндекс.Директа">Показать быстрые улучшения</button>
        </div>
      ` : ''}
      <p><strong>Безопасность:</strong> аудит read-only. Рекомендации являются черновиками; изменения в Яндекс.Директ не применяются.</p>
    </section>
  `;
}

function businessContextFilledCount(context = businessContext) {
  const fields = [
    'brandName',
    'businessNiche',
    'productSummary',
    'targetAudience',
    'geography',
    'seasonality',
    'mainOffers',
    'conversionActions',
    'businessConstraints',
    'negativeTopics',
    'landingPageNotes',
    'manualNotes',
    'memoryNotes',
  ];
  return fields.filter((field) => String(context?.[field] || '').trim()).length;
}

function businessContextCopyText(context = businessContext) {
  const labels = [
    ['brandName', 'Бренд'],
    ['businessNiche', 'Ниша'],
    ['productSummary', 'Что продаём'],
    ['targetAudience', 'Целевая аудитория'],
    ['geography', 'География'],
    ['seasonality', 'Сезонность'],
    ['mainOffers', 'Основные офферы'],
    ['conversionActions', 'Целевые действия'],
    ['averageOrderValue', 'Средний чек / ценность лида'],
    ['businessConstraints', 'Ограничения бизнеса'],
    ['negativeTopics', 'Нерелевантные темы'],
    ['landingPageNotes', 'Посадочные страницы'],
    ['competitorNotes', 'Конкуренты'],
    ['manualNotes', 'Ручные заметки'],
    ['memoryNotes', 'Память проекта'],
  ];
  return labels
    .map(([key, label]) => `${label}: ${context?.[key] || '—'}`)
    .join('\n');
}

function renderBusinessContextPanel(compact = false) {
  const client = currentClient();
  const filledCount = businessContextFilledCount();
  const statusText = filledCount >= 6 ? 'Хорошо заполнен' : filledCount ? 'Заполнен частично' : 'Не заполнен';
  if (!client.id) {
    return `<section class="panel emptyStatePanel compact"><h3>Контекст бизнеса</h3><p>Создайте клиента, чтобы сохранить бизнес-контекст и память проекта.</p><button class="approveButton" data-go-view="clients">Создать клиента</button></section>`;
  }
  if (compact) {
    return `
      <section class="panel compact">
        <div class="panelHeader">
          <div>
            <h3>Контекст бизнеса</h3>
            <p>${filledCount ? `${escapeHtml(businessContext?.brandName || client.name)} · ${escapeHtml(businessContext?.businessNiche || 'ниша не указана')}` : 'Заполните бренд, нишу, офферы и ограничения, чтобы AI анализировал кампании не только по метрикам.'}</p>
          </div>
          <span class="aiStatusBadge ${filledCount ? 'ready' : 'pending'}">${escapeHtml(statusText)}</span>
        </div>
        <div class="heroActions">
          <button class="secondaryButton" data-go-view="business-context">Открыть контекст бизнеса</button>
        </div>
      </section>
    `;
  }
  const context = businessContext || {};
  const field = (name, label, placeholder = '') => `
    <label class="authField">
      <span>${label}</span>
      <textarea name="${name}" rows="3" placeholder="${escapeHtml(placeholder)}">${escapeHtml(context[name] || '')}</textarea>
    </label>
  `;
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <span class="eyebrow">Память проекта</span>
          <h3>Контекст бизнеса</h3>
          <p>Эти данные попадут в доверенный AI-контекст: бренд, ниша, офферы, ограничения, нерелевантные темы и заметки специалиста.</p>
        </div>
        <span class="aiStatusBadge ${filledCount ? 'ready' : 'pending'}">${formatNumberSafe(filledCount)} полей · ${escapeHtml(statusText)}</span>
      </div>
      ${businessContextStatus ? `<div class="authStatus integrationStatus">${escapeHtml(businessContextStatus)}</div>` : ''}
      <form class="authForm" data-business-context-form>
        <div class="clientSettingsGrid">
          <label class="authField"><span>Бренд</span><input name="brandName" value="${escapeHtml(context.brandName || '')}" placeholder="Название бренда или проекта" /></label>
          <label class="authField"><span>Ниша / категория бизнеса</span><input name="businessNiche" value="${escapeHtml(context.businessNiche || '')}" placeholder="Например: мебель, стоматология, отель" /></label>
          ${field('productSummary', 'Что продаём', 'Ключевые продукты, услуги, пакеты')}
          ${field('targetAudience', 'Целевая аудитория', 'Кто покупает, сегменты, боли')}
          ${field('geography', 'География', 'Города, регионы, ограничения доставки/оказания услуги')}
          ${field('seasonality', 'Сезонность', 'Пики спроса, низкий сезон, события')}
          ${field('mainOffers', 'Основные офферы', 'Акции, преимущества, УТП')}
          ${field('conversionActions', 'Целевые действия', 'Заявка, звонок, бронь, покупка, квиз')}
          ${field('averageOrderValue', 'Средний чек / ценность лида', 'Средний чек, маржа, LTV или ценность заявки')}
          ${field('leadValueNotes', 'Заметки по ценности лида', 'Какие лиды качественные/некачественные')}
          ${field('businessConstraints', 'Ограничения бизнеса', 'Бюджет, склад, сроки, юридические ограничения')}
          ${field('negativeTopics', 'Нерелевантные темы / минус-направления', 'Запросы и темы, которые не подходят бизнесу')}
          ${field('landingPageNotes', 'Посадочные страницы и заметки', 'URL, структура, важные блоки. Автопроверки страниц пока нет.')}
          ${field('competitorNotes', 'Конкуренты', 'Конкуренты, отличие, ценовое позиционирование')}
          ${field('manualNotes', 'Ручные заметки специалиста', 'Что важно помнить при аудите и оптимизации')}
          ${field('memoryNotes', 'Память проекта', 'Сохранённые выводы AI и важные решения по проекту')}
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
  const nextTarget = nextAction.targetView || 'dashboard';
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">📊 Обзор</span>
      <h2>${hasClient ? escapeHtml(client.name) : 'Подготовьте первого клиента к анализу'}</h2>
      <p>${hasClient ? 'Здесь видно, что уже готово, что мешает синхронизации и какой следующий шаг даст максимум пользы.' : 'Создайте клиента, чтобы подключить данные, запустить синхронизацию и открыть AI-анализ.'}</p>
    </div>
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Следующий шаг</h3>
          <p>${escapeHtml(nextAction.description || nextAction.label || '')}</p>
        </div>
        <span class="aiStatusBadge ${badgeClassForStatus(nextAction.status)}">${escapeHtml(compactStatusLabel(nextAction.status))}</span>
      </div>
      <div class="authStatus integrationStatus"><strong>${escapeHtml(nextAction.nextAction)}</strong></div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Готовность</span><strong>${formatNumberSafe(readyCount)} / ${formatNumberSafe(readiness.length)}</strong></article>
        <article class="kpi blue"><span>Клиент</span><strong>${hasClient ? 'Готово' : 'Нужно действие'}</strong></article>
        <article class="kpi orange"><span>Данные</span><strong>${hasPerformanceData() ? 'Готово' : 'Нет данных'}</strong></article>
        <article class="kpi orange"><span>Кандидаты в минус-слова</span><strong>${formatNumberSafe(perfSummary?.searchQueryInsights?.candidateNegativeKeywords || 0)}</strong></article>
      </div>
      <div class="heroActions">
        ${renderActionButton('Клиенты', 'data-go-view="clients"')}
        ${renderActionButton('Контекст бизнеса', 'data-go-view="business-context"')}
        ${renderActionButton('Интеграции', 'data-go-view="integrations"')}
        ${renderActionButton(syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию', `data-sync-client ${canRunSync() && !syncLoading ? '' : 'disabled'}`, 'primary')}
        ${renderActionButton('Перейти к шагу', `data-go-view="${escapeHtml(nextTarget)}"`, 'primary')}
      </div>
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
    </section>
    ${renderReadinessPanel(readiness, nextAction)}
    ${!hasClient ? `
      <section class="panel emptyStatePanel">
        <h3>Нет клиента</h3>
        <p>Создайте клиента, чтобы подключить данные и запустить анализ. После этого DirectPilot покажет готовность, синхронизацию, сводку и AI-план.</p>
        <button class="approveButton" data-view="clients">Перейти к клиентам</button>
      </section>
    ` : `
      ${renderSyncCenter()}
      ${renderBusinessContextPanel(true)}
      ${renderSyncDiagnosticsPanel(true)}
      ${renderYesterdaySummaryPanel()}
      ${renderYandexDirectAuditPanel(true)}
      ${renderPerformanceSummaryPanel()}
    `}
  `);
}

function renderClients() {
  const selected = currentClient();
  const hasSelectedClient = Boolean(selected.id);
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">👥 Клиенты</span><h2>Клиенты как отдельные сущности</h2><p>Создайте отдельную карточку клиента для каждого аккаунта/проекта и укажите логин Яндекс.Директа и счётчик Метрики.</p></div>
    <section class="panel clientConnectPanel">
      <div>
        <h3>Добавить клиента</h3>
        <p>При доступном backend клиенты сохраняются в API и загружаются оттуда при каждом обновлении страницы. Если backend недоступен — включается fallback режим c localStorage.</p>
      </div>
      <form class="clientConnectForm" data-client-form>
        <input name="name" value="${escapeHtml(clientDraftName)}" placeholder="Название клиента" autocomplete="organization" required />
        <input name="directLogin" value="${escapeHtml(clientDraftDirectLogin)}" placeholder="Логин Яндекс.Директа" autocomplete="off" />
        <input name="metricaCounter" value="${escapeHtml(clientDraftMetricaCounter)}" placeholder="ID счётчика Метрики" inputmode="numeric" autocomplete="off" />
        <button class="approveButton" type="submit">Добавить клиента</button>
      </form>
      <div class="authStatus integrationStatus">${escapeHtml(backendClientsStatus)}</div>
      ${clientFormStatus ? `<div class="authStatus integrationStatus">${escapeHtml(clientFormStatus)}</div>` : ''}
    </section>
    ${hasSelectedClient ? `
      <section class="panel clientConnectPanel">
        <div>
          <h3>Настройки клиента «${escapeHtml(selected.name)}»</h3>
          <p>Настройки относятся только к выбранному клиенту. Привязка Яндекса настраивается отдельно во вкладке интеграций.</p>
        </div>
        <form class="clientConnectForm" data-client-settings-form>
          <input name="name" value="${escapeHtml(selected.name)}" placeholder="Название клиента" autocomplete="organization" required />
          <input name="directLogin" value="${escapeHtml(selected.directLogin === 'Не подключен' ? '' : selected.directLogin)}" placeholder="Логин Яндекс.Директа" autocomplete="off" />
          <input name="metricaCounter" value="${escapeHtml(selected.metricaCounter === 'Не подключен' ? '' : selected.metricaCounter)}" placeholder="ID счётчика Метрики" inputmode="numeric" autocomplete="off" />
          <input name="targetCpa" value="${escapeHtml(selected.targetCpa ?? '')}" placeholder="Целевой CPA" inputmode="numeric" autocomplete="off" />
          <input name="conversionGoalIds" value="${escapeHtml(selected.conversionGoalIds ?? selected.mainGoalId ?? '')}" placeholder="ID целей Метрики: например 123456, 789012" autocomplete="off" />
          <small>Используются для расчёта целевых конверсий, CPA и AI-анализа.</small>
          <input name="mainGoalId" value="${escapeHtml(selected.mainGoalId ?? '')}" placeholder="Основная цель (backward compatibility)" autocomplete="off" />
          <textarea name="notes" rows="3" placeholder="Заметки по клиенту">${escapeHtml(selected.notes ?? '')}</textarea>
          <button class="approveButton" type="submit">Сохранить настройки</button>
          <button class="secondaryButton" type="button" data-delete-client="${escapeHtml(selected.id)}">Удалить клиента</button>
        </form>
      </section>
    ` : ''}
    ${accountClients.length ? `
      <div class="clientGrid">
        ${accountClients.map((client) => `
          <button class="clientCard ${client.id === selectedClientId ? 'selected' : ''}" data-client-id="${client.id}">
            <span>${client.segment}</span>
            <strong>${client.name}</strong>
            <div class="clientStats"><small>Direct: ${client.directLogin}</small><small>Метрика: ${client.metricaCounter}</small><small>Score ${client.score}/100</small></div>
            <em>${client.trend}</em>
          </button>
        `).join('')}
      </div>
    ` : `
      <section class="panel emptyStatePanel compact">
        <h3>Клиентов пока нет</h3>
        <p>Мы убрали все демо-аккаунты из личного кабинета. Добавьте реального клиента и подключите его источники данных.</p>
      </section>
    `}
    ${perfSummary ? `
      <section class="panel">
        <h3>Сводка эффективности (${escapeHtml(perfSummary.message)})</h3>
        <p>Расход: ${perfSummary.totals.cost} ₽ · Показы: ${perfSummary.totals.impressions} · Клики: ${perfSummary.totals.clicks} · Конверсии по целям: ${perfSummary.goalConversionsTotal ?? '—'}</p>
        <p>Средний CPC: ${perfSummary.totals.avg_cpc} · CPA по целям: ${perfSummary.totals.cpa ?? '—'}</p>
      </section>
    ` : ''}
  `);
}

function renderAudit() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">⚡ AI-аудит</span><h2>Проблемы, которые влияют на эффективность</h2><p>Каждый пункт содержит доказательство, объект в Директе и рекомендуемое действие.</p></div>
    ${auditIssues.length ? `
      <div class="auditList">
        ${auditIssues.map((issue) => `
          <article class="auditItem ${issue.priority}">
            <div class="priorityBadge">${priorityLabel(issue.priority)}</div>
            <div>
              <h3>${issue.title}</h3>
              <span>${issue.object}</span>
              <p>${issue.evidence}</p>
              <strong>Рекомендация: ${issue.action}</strong>
            </div>
          </article>
        `).join('')}
      </div>
    ` : `<section class="panel emptyStatePanel compact"><h3>Аудит пока пуст</h3><p>Подключите клиента к Директу и Метрике, чтобы AI-аудит работал на реальных данных.</p></section>`}
  `);
}

function renderClientAiRecommendations() {
  if (clientAiLoading) {
    return '<section class="panel aiDraftPanel"><h3>AI анализирует клиента...</h3><p>Собираем контекст клиента, аудит, кампании и guardrails.</p></section>';
  }
  if (clientAiError) {
    return `<section class="panel aiDraftPanel"><h3>AI-рекомендации недоступны</h3><p>${escapeHtml(clientAiError)}</p><p>Free/custom модели могут часто получать rate limit.</p><button class="secondaryButton" type="button" data-ai-economy-fallback="recommendations">Повторить на модели Эконом</button></section>`;
  }
  if (!clientAiRecommendations) return '';
  return `
    <section class="panel aiDraftPanel">
      <div class="panelHeader">
        <div>
          <h3>AI-черновик по контексту клиента</h3>
          <p>${escapeHtml(clientAiRecommendations.summary)}</p>
        </div>
        <span class="aiStatusBadge ready">AI-план</span>
      </div>
      <div class="aiDraftGrid">
        ${clientAiRecommendations.recommendations.map((item) => `
          <article>
            <div class="actionTop"><span>${escapeHtml(item.risk)} риск</span><strong>${item.requires_approval ? 'Нужно согласование' : 'Только чтение'}</strong></div>
            <h4>${escapeHtml(item.title)}</h4>
            <ul>${item.evidence.map((fact) => `<li>${escapeHtml(fact)}</li>`).join('')}</ul>
            <p><strong>Эффект:</strong> ${escapeHtml(item.expected_impact)}</p>
            <p><strong>Следующий шаг:</strong> ${escapeHtml(item.next_step)}</p>
          </article>
        `).join('')}
      </div>
    </section>
  `;
}

function renderRecommendations() {
  const campaignsCount = perfSummary?.campaigns?.length || 0;
  const issueCount = perfSummary?.campaigns?.reduce((sum, item) => sum + (item.issue_flags?.length || 0), 0) || 0;
  const totals = perfSummary?.totals || {};
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">✨ Рекомендации</span><h2>Действия с объяснениями и контролем риска</h2><p>В production каждая карточка будет иметь dry-run, diff, approval и rollback-данные.</p></div>
    <section class="panel aiRecommendationCta">
      <div>
        <h3>Сформировать AI-рекомендации по клиентскому контексту</h3>
        <p>${canRunAiAnalysis() ? `AI будет использовать конверсии выбранных целей Директа. ${perfSummary?.hasGoalData ? '' : 'Данные по целям пока недоступны, выводы по CPA ограничены.'}` : 'AI пока не видит статистику кампаний. Сначала запустите синхронизацию.'}</p>
      </div>
      <button class="approveButton" data-client-ai-recommendations ${clientAiLoading ? 'disabled' : ''}>${clientAiLoading ? 'Генерируем...' : 'Сгенерировать AI-черновик'}</button>
    </section>
    <section class="panel">
      <div class="panelHeader">
        <h3>Предпросмотр данных</h3>
        <span class="aiStatusBadge ${canRunAiAnalysis() ? 'ready' : 'pending'}">${canRunAiAnalysis() ? 'Реальные данные доступны' : 'Нужна статистика'}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Расход</span><strong>${formatMoneySafe(totals.cost)}</strong></article>
        <article class="kpi blue"><span>Конверсии по целям</span><strong>${perfSummary?.goalConversionsTotal == null ? '—' : formatNumberSafe(perfSummary.goalConversionsTotal)}</strong></article>
        <article class="kpi orange"><span>Кампании</span><strong>${formatNumberSafe(campaignsCount)}</strong></article>
        <article class="kpi green"><span>Флаги</span><strong>${formatNumberSafe(issueCount)}</strong></article>
      </div>
      <p>Цели: ${escapeHtml(perfSummary?.selectedGoalIds?.join(', ') || perfSummary?.selectedGoalId || currentClient().mainGoalId || 'не указаны')} · Конверсии по целям: ${formatNumberSafe(perfSummary?.goalConversionsTotal || 0)}</p>
    </section>
    ${renderClientAiRecommendations()}
    ${recommendations.length ? `
      <div class="recommendationGrid">
        ${recommendations.map((item) => `
          <article class="actionCard">
            <div class="actionTop"><span>${item.risk} риск</span><strong>${item.impact}</strong></div>
            <h3>${item.title}</h3>
            <p>${item.reason}</p>
            <small>${item.objects}</small>
            <div class="actionButtons"><button>Подробнее</button><button class="approveButton">Сохранить как черновик</button></div>
          </article>
        `).join('')}
      </div>
    ` : `<section class="panel emptyStatePanel compact"><h3>Рекомендаций пока нет</h3><p>Нажмите «Сгенерировать AI-черновик» после добавления клиента или подключите реальные источники данных.</p></section>`}
  `);
}

function campaignMatchesOptimizationFilter(campaign) {
  const flags = campaign.issue_flags || [];
  if (optimizationFilter === 'all') return true;
  if (optimizationFilter === 'critical') return campaign.severity === 'critical';
  if (optimizationFilter === 'warning') return campaign.severity === 'warning';
  if (optimizationFilter === 'opportunities') return campaign.severity === 'info' || flags.includes('promising_campaign');
  if (optimizationFilter === 'no_conversions') return flags.includes('spend_without_conversions');
  if (optimizationFilter === 'high_cpa') return flags.includes('high_cpa');
  if (optimizationFilter === 'low_ctr') return flags.includes('low_ctr');
  if (optimizationFilter === 'goal_unavailable') return ['unavailable', 'fallback_total_when_goal_unavailable', 'metrika_goal_unavailable'].includes(campaign.conversion_source);
  return true;
}

function renderExecutionPreview(preview) {
  if (!preview) return '';
  const renderList = (items) => (items?.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '<p>—</p>');
  return `
    <div class="authStatus integrationStatus">
      <strong>Это только предпросмотр. Изменения в Яндекс.Директ не применяются.</strong>
      <p>${escapeHtml(preview.summary || '')}</p>
      <p>Применение отключено: ${preview.can_apply || preview.apply_enabled ? 'нет' : 'да'}</p>
      <div class="clientSettingsGrid">
        <div><strong>Что будет подготовлено</strong>${renderList(preview.would_do || [])}</div>
        <div><strong>Какие данные нужны</strong>${renderList(preview.required_data || [])}</div>
        <div><strong>Чего не хватает</strong>${renderList(preview.missing_data || [])}</div>
        <div><strong>Проверки безопасности</strong>${renderList(preview.safety_checks || [])}</div>
        <div><strong>Предупреждения</strong>${renderList(preview.warnings || [])}</div>
      </div>
      <p><strong>Следующий шаг:</strong> ${escapeHtml(preview.next_step || '')}</p>
    </div>
  `;
}

function renderOptimization() {
  const client = currentClient();
  const campaigns = (perfSummary?.campaigns || []).filter(campaignMatchesOptimizationFilter);
  const actions = optimizationPlan?.actions || [];
  const savedCounts = getOptimizationActionCounts();
  const previewReadyCount = (savedCounts.approved || 0) + (savedCounts.reviewed || 0);
  const savedActionFilters = ['all', 'draft', 'reviewed', 'approved', 'rejected', 'needs_changes'];
  const filters = [
    ['all', 'Все'],
    ['critical', 'Критично'],
    ['warning', 'Предупреждения'],
    ['opportunities', 'Возможности'],
    ['no_conversions', 'Без конверсий'],
    ['high_cpa', 'Высокий CPA'],
    ['low_ctr', 'Низкий CTR'],
    ['goal_unavailable', 'Данные по целям недоступны'],
  ];
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">🎯 Оптимизация</span>
      <h2>Оптимизация: диагностика, план, согласование</h2>
      <p>${escapeHtml(client.name)} · цели: ${escapeHtml(perfSummary?.selectedGoalIds?.join(', ') || client.conversionGoalIds || client.mainGoalId || 'не указаны')} · ${perfSummary?.hasGoalData ? 'Данные по выбранным целям Директа загружены.' : 'Проверьте загрузку конверсий по целям.'}</p>
      <div class="heroActions">
        <button class="secondaryButton" data-load-summary ${perfLoading ? 'disabled' : ''}>Обновить сводку</button>
        <button class="approveButton" data-load-optimization-plan ${optimizationPlanLoading ? 'disabled' : ''}>${optimizationPlanLoading ? 'Формируем...' : 'AI-план'}</button>
        <button class="secondaryButton" data-copy-optimization-plan ${actions.length ? '' : 'disabled'}>Скопировать план</button>
      </div>
      ${optimizationPlanStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationPlanStatus)}</div>` : ''}
    </div>
    ${renderSyncDiagnosticsPanel(true)}
    ${renderYandexDirectAuditPanel()}
    <section class="panel">
      <div class="panelHeader">
        <div>
          <span class="eyebrow">Этап 1</span>
          <h3>Диагностика</h3>
          <p>${perfSummary?.hasGoalData ? 'CPA и диагностика используют конверсии по выбранным целям.' : 'Данные по целям недоступны: выводы по CPA ограничены, проверьте цели и синхронизацию.'}</p>
        </div>
        <span class="aiStatusBadge ${perfSummary?.campaigns?.length ? 'ready' : 'pending'}">${formatNumberSafe(perfSummary?.campaigns?.length || 0)} кампаний</span>
      </div>
      <div class="heroActions">
        ${filters.map(([value, label]) => `<button class="${optimizationFilter === value ? 'approveButton' : 'secondaryButton'}" data-optimization-filter="${value}">${label}</button>`).join('')}
      </div>
      ${campaigns.length ? `<div class="featureGrid">
        ${campaigns.map((campaign) => `
          <article class="featureCard">
            <span class="featureIcon">${campaign.severity === 'critical' ? '⛔' : campaign.severity === 'warning' ? '⚠️' : campaign.severity === 'info' ? '📈' : '✅'}</span>
            <h3>${escapeHtml(campaign.campaign_name)}</h3>
            <p>${escapeHtml(campaign.diagnostic_explanation || '')}</p>
            <small>Цели ${escapeHtml(campaign.goal_ids || perfSummary?.selectedGoalIds?.join(', ') || '—')} · Расход ${formatMoneySafe(campaign.cost)} · клики ${formatNumberSafe(campaign.clicks)} · показы ${formatNumberSafe(campaign.impressions)} · конверсии по целям ${campaign.goal_conversions == null ? '—' : formatNumberSafe(campaign.goal_conversions)} · CPA по целям ${campaign.cpa_used == null ? '—' : formatMoneySafe(campaign.cpa_used)} · CTR ${formatPercentSafe(campaign.ctr)}</small>
            <p><strong>Фокус:</strong> ${escapeHtml(campaign.recommended_focus || '')}</p>
            <p><strong>Флаги:</strong> ${escapeHtml(renderIssueFlags(campaign.issue_flags))}</p>
          </article>
        `).join('')}
      </div>` : `<div class="emptyStatePanel compact"><h3>Нет кампаний для фильтра</h3><p>Обновите сводку или смените фильтр.</p></div>`}
    </section>
    ${renderSearchQueryInsightsPanel()}
    <section class="panel">
      <div class="panelHeader">
        <div>
          <span class="eyebrow">Этап 3</span>
          <h3>Согласование</h3>
          <p>Это черновики действий. Изменения в Яндекс.Директ не применяются. Одобрение фиксирует решение, но не запускает изменение в рекламном кабинете.</p>
        </div>
        <span class="aiStatusBadge ${savedCounts.total ? 'ready' : 'pending'}">${formatNumberSafe(savedCounts.total)} черновиков</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi blue"><span>Черновики</span><strong>${formatNumberSafe(savedCounts.draft)}</strong></article>
        <article class="kpi green"><span>Просмотрено</span><strong>${formatNumberSafe(savedCounts.reviewed)}</strong></article>
        <article class="kpi green"><span>Одобрено</span><strong>${formatNumberSafe(savedCounts.approved)}</strong></article>
        <article class="kpi orange"><span>Отклонено</span><strong>${formatNumberSafe(savedCounts.rejected)}</strong></article>
        <article class="kpi blue"><span>Нужны правки</span><strong>${formatNumberSafe(savedCounts.needs_changes)}</strong></article>
        <article class="kpi orange"><span>Готово к предпросмотру</span><strong>${formatNumberSafe(previewReadyCount)}</strong></article>
      </div>
      <div class="heroActions">
        <button class="approveButton" type="button" data-save-optimization-actions ${optimizationActionsLoading ? 'disabled' : ''}>${optimizationActionsLoading ? 'Сохраняем...' : 'Сохранить текущий план как черновики'}</button>
        <button class="secondaryButton" type="button" data-load-optimization-actions ${optimizationActionsLoading ? 'disabled' : ''}>Обновить список</button>
        ${savedActionFilters.map((statusValue) => `<button class="${optimizationActionFilter === statusValue ? 'approveButton' : 'secondaryButton'}" type="button" data-optimization-action-filter="${statusValue}">${statusValue === 'all' ? 'Все' : optimizationStatusLabel(statusValue)}</button>`).join('')}
      </div>
      ${optimizationActionsStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationActionsStatus)}</div>` : ''}
      ${optimizationExecutionPreviewStatus ? `<div class="authStatus integrationStatus">${escapeHtml(optimizationExecutionPreviewStatus)}</div>` : ''}
      ${optimizationActions.length ? `<div class="featureGrid">
        ${optimizationActions.map((action) => `
          <article class="featureCard">
            <span class="featureIcon">${action.status === 'approved' ? '✅' : action.status === 'rejected' ? '⛔' : action.status === 'needs_changes' ? '⚠️' : '📝'}</span>
            <h3>${escapeHtml(action.issue)}</h3>
            <small>${escapeHtml(actionSourceLabel(action.source))} · ${escapeHtml(severityLabel(action.severity || 'info'))} · ${escapeHtml(action.campaignName || 'аккаунт')} · ${escapeHtml(optimizationStatusLabel(action.status))}</small>
            <p><strong>Обоснование:</strong> ${escapeHtml(action.evidence || '—')}</p>
            <p><strong>Черновик действия:</strong> ${escapeHtml(action.draftAction)}</p>
            <p>${escapeHtml(action.safetyNote || 'Черновик действия. Изменения в Яндекс.Директ не применялись.')}</p>
            <label class="authField">
              <span>Комментарий</span>
              <textarea rows="2" data-optimization-action-comment="${escapeHtml(action.id)}">${escapeHtml(action.userComment || '')}</textarea>
            </label>
            <div class="heroActions">
              <button class="secondaryButton" type="button" data-update-optimization-action="${escapeHtml(action.id)}" data-action-status="reviewed">Просмотрено</button>
              <button class="approveButton" type="button" data-update-optimization-action="${escapeHtml(action.id)}" data-action-status="approved">Одобрить</button>
              <button class="secondaryButton" type="button" data-update-optimization-action="${escapeHtml(action.id)}" data-action-status="rejected">Отклонить</button>
              <button class="secondaryButton" type="button" data-update-optimization-action="${escapeHtml(action.id)}" data-action-status="needs_changes">На доработку</button>
              <button class="secondaryButton" type="button" data-load-execution-preview="${escapeHtml(action.id)}">Этап 4: предпросмотр применения</button>
            </div>
            ${renderExecutionPreview(optimizationExecutionPreviewsByActionId[action.id])}
          </article>
        `).join('')}
      </div>` : '<div class="emptyStatePanel compact"><h3>Нет сохранённых черновиков</h3><p>Сохраните план оптимизации как черновики, чтобы согласовать действия и добавить комментарии.</p><button class="approveButton" type="button" data-save-optimization-actions>Сохранить план как черновики</button></div>'}
    </section>
    <section class="panel">
      <div class="panelHeader">
        <div>
          <span class="eyebrow">Этап 2</span>
          <h3>План действий</h3>
          <p>Это manual review. Изменения в Яндекс.Директ не применяются автоматически.</p>
        </div>
        <span class="aiStatusBadge pending">${formatNumberSafe(actions.length)} действий</span>
      </div>
      ${actions.length ? `<div class="auditList">
        ${actions.map((action) => `
          <article class="auditItem ${action.severity === 'critical' ? 'high' : action.severity === 'warning' ? 'medium' : 'low'}">
            <div class="priorityBadge">${escapeHtml(action.severity)}</div>
            <div>
              <h3>${escapeHtml(action.issue)}</h3>
              <span>${escapeHtml(action.campaign_name || 'Аккаунт')}</span>
              <p>${escapeHtml(action.evidence)}</p>
              <strong>${escapeHtml(action.draft_action)}</strong>
              <p>${escapeHtml(action.safety_note)}</p>
              <button class="secondaryButton" data-copy-text="${escapeHtml(`${action.issue}\n${action.evidence}\n${action.draft_action}`)}">Скопировать рекомендацию</button>
              <button class="secondaryButton" type="button">Отметить как просмотрено</button>
            </div>
          </article>
        `).join('')}
      </div>` : `<div class="emptyStatePanel compact"><h3>План действий ещё не сформирован</h3><p>Сформируйте AI-план, чтобы увидеть черновики безопасных действий. Изменения в Яндекс.Директ не применяются.</p><button class="approveButton" data-load-optimization-plan ${optimizationPlanLoading ? 'disabled' : ''}>${optimizationPlanLoading ? 'Формируем...' : 'Сформировать AI-план'}</button></div>`}
    </section>
  `);
}

function renderReports() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">📄 Отчёт</span><h2>Weekly summary для клиента</h2><p>Готовый текстовый каркас отчёта, который агентство сможет отправлять клиенту каждую неделю.</p></div>
    <div class="reportGrid">
      ${Object.entries({ happened: 'Что произошло', done: 'Что сделал специалист', next: 'Что делаем дальше' }).map(([key, title]) => `
        <article class="panel reportCard"><h3>${title}</h3><ul>${reportBullets[key].map((item) => `<li>${item}</li>`).join('')}</ul></article>
      `).join('')}
    </div>
  `);
}

function renderIntegrations() {
  const client = currentClient();
  const accounts = clientYandexIntegration?.available_accounts || integrationStatus.accounts || [];
  const boundAccount = clientYandexIntegration?.bound_account;
  const clientConnected = Boolean(boundAccount);
  const selectedAccountId = boundAccount?.id || accounts[0]?.id || '';
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">🔌 Интеграции</span><h2>Подключите рабочие источники данных</h2><p>Яндекс.Директ и Метрика подключаются через OAuth. Один доступ содержит scopes direct:api, metrika:read и login:info.</p></div>
    ${renderBackendApiConfig()}
    <section class="panel clientSourcePanel">
      <div>
        <h3>${client.id ? `Источники клиента «${client.name}»` : 'Сначала добавьте клиента'}</h3>
        <p>Direct login: ${client.directLogin} · Метрика: ${client.metricaCounter}. OAuth-доступ хранится на backend, а клиентская карточка связывает этот доступ с конкретным проектом.</p>
      </div>
      <button class="approveButton" data-view="clients">${client.id ? 'Изменить карточку клиента' : 'Добавить клиента'}</button>
    </section>
    <div class="integrationGrid">
      <article class="integrationCard primaryIntegration">
        <div class="integrationTop"><span>Яндекс.Директ</span><strong>${clientConnected ? `Привязан: ${escapeHtml(boundAccount.login || boundAccount.display_name || boundAccount.id)}` : 'Не привязан'}</strong></div>
        <h3>Аккаунт клиента</h3>
        <p>${client.id ? 'Привяжите один из доступных OAuth-аккаунтов к выбранному клиенту. Новые клиенты остаются чистыми, пока вы явно не выберете аккаунт.' : 'Сначала добавьте клиента.'}</p>
        ${client.id ? `
          <form class="authForm" data-yandex-bind-form>
            <label>
              <span>Доступные аккаунты</span>
              <select name="yandexAccountId" ${accounts.length ? '' : 'disabled'}>
                ${accounts.length ? accounts.map((item) => `<option value="${item.id}" ${item.id === selectedAccountId ? 'selected' : ''}>${escapeHtml(item.login || item.display_name || item.id)}</option>`).join('') : '<option value="">Нет подключённых аккаунтов</option>'}
              </select>
            </label>
            <button class="approveButton" type="submit" ${accounts.length ? '' : 'disabled'}>Привязать аккаунт</button>
            <button class="secondaryButton" type="button" data-unbind-yandex ${clientConnected ? '' : 'disabled'}>Отвязать</button>
          </form>
        ` : ''}
        <div class="authStatus integrationStatus">${escapeHtml(clientYandexStatus || (clientConnected ? 'Яндекс-аккаунт привязан к этому клиенту.' : 'Сначала привяжите Яндекс-аккаунт к этому клиенту.'))}</div>
        <code>GET /api/v1/auth/yandex/start</code>
        <button class="secondaryButton" type="button" data-refresh-yandex-status>Обновить статус Яндекса</button>
        <button class="approveButton" data-integration="yandex-direct">${accounts.length ? 'Подключить ещё аккаунт' : 'Подключить Яндекс.Директ'}</button>
      </article>
      <article class="integrationCard primaryIntegration">
        <div class="integrationTop"><span>Доступные аккаунты</span><strong>${accounts.length}</strong></div>
        <h3>Глобальный OAuth-доступ</h3>
        <p>OAuth остаётся общим списком доступов, но подключённым к клиенту считается только явно привязанный аккаунт.</p>
        <code>${accounts.map((item) => escapeHtml(item.login || item.display_name || item.id)).join(', ') || 'Нет аккаунтов'}</code>
        <button class="approveButton" data-integration="yandex-metrica">${accounts.length ? 'Обновить OAuth-доступ' : 'Подключить Яндекс.Метрику'}</button>
      </article>
      <article class="integrationCard">
        <div class="integrationTop"><span>CRM</span><strong>План</strong></div>
        <h3>Качество лидов и продажи</h3>
        <p>Позволит оптимизировать рекламу не по заявкам, а по выручке и марже.</p>
        <button data-integration="crm">Оставить в плане</button>
      </article>
    </div>
    ${integrationStatus.message ? `<div class="authStatus integrationStatus">${integrationStatus.message}</div>` : ''}
  `);
}

function renderAiModelSettings() {
  const preset = activeAiPresetInfo();
  const model = activeAiModelInfo();
  const modelOptions = getAiModelOptions();
  const presetOptions = getAiPresetOptions();
  const selectedModelValue = isCustomAiModel() ? CUSTOM_MODEL_VALUE : activeAiModel();
  const customModelActive = selectedModelValue === CUSTOM_MODEL_VALUE || aiPreset === 'custom';
  const resolvedModel = activeAiModel();
  const resolvedMaxTokens = activeAiMaxTokens();
  const costLabel = { low: 'низкая стоимость', medium: 'средняя стоимость', high: 'дороже', unknown: 'стоимость неизвестна' }[model.cost_tier || 'unknown'] || 'стоимость неизвестна';
  const freeModelWarning = resolvedModel.includes(':free')
    ? 'Free-модели часто получают rate limit у провайдера. Для стабильной работы выберите модель из списка.'
    : '';
  const customModelWarning = customModelActive
    ? 'Своя/free модель может быть нестабильной: возможны лимиты, 429 и временная недоступность.'
    : '';
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>AI-модель</h3>
          <p>${escapeHtml(aiPresetLabel(preset))} · ${escapeHtml(resolvedModel)} · лимит ${formatNumberSafe(resolvedMaxTokens)} tokens</p>
        </div>
        <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'OpenRouter подключён' : 'OpenRouter не настроен'}</span>
      </div>
      <p>${escapeHtml(aiStatus.message || '')}</p>
      ${customModelWarning ? `<div class="authStatus">${escapeHtml(customModelWarning)}</div>` : ''}
      ${freeModelWarning ? `<div class="authStatus aiError">${escapeHtml(freeModelWarning)}</div>` : ''}
      <details>
        <summary class="secondaryButton">Настройки модели</summary>
        <p>Режимы Эконом/Баланс/Максимум — это настройки DirectPilot AI. OpenRouter получает конкретную модель и лимит токенов.</p>
        <p>Режим влияет на модель по умолчанию, лимит ответа и подробность ответа. Дорогие модели могут быстрее расходовать баланс OpenRouter.</p>
        <p>Эконом — быстрые и дешёвые регулярные проверки. Баланс — основной режим для анализа кампаний и запросов. Максимум — сложные аудиты, спорные выводы, глубокий разбор.</p>
        <p><a href="https://openrouter.ai/models" target="_blank" rel="noopener noreferrer">Каталог моделей OpenRouter</a></p>
        <div class="clientSettingsGrid">
          <label class="authField">
            <span>Режим</span>
            <select data-ai-preset>
              ${presetOptions.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === aiPreset ? 'selected' : ''}>${escapeHtml(aiPresetLabel(item))} · ${escapeHtml(item.cost_tier || 'unknown')}</option>`).join('')}
              <option value="custom" ${aiPreset === 'custom' ? 'selected' : ''}>Своя модель</option>
            </select>
          </label>
          <label class="authField">
            <span>Модель</span>
            <select data-ai-model>
              ${modelOptions.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === selectedModelValue ? 'selected' : ''}>${escapeHtml(item.label || item.name || item.id)} · ${escapeHtml(item.cost_tier || 'unknown')}</option>`).join('')}
              <option value="${CUSTOM_MODEL_VALUE}" ${selectedModelValue === CUSTOM_MODEL_VALUE ? 'selected' : ''}>Своя модель OpenRouter</option>
            </select>
          </label>
          <label class="authField">
            <span>Детализация</span>
            <select data-ai-max-tokens-mode>
              <option value="compact" ${aiMaxTokensMode === 'compact' ? 'selected' : ''}>compact</option>
              <option value="normal" ${aiMaxTokensMode === 'normal' ? 'selected' : ''}>normal</option>
              <option value="detailed" ${aiMaxTokensMode === 'detailed' ? 'selected' : ''}>detailed</option>
            </select>
          </label>
          ${customModelActive ? `
            <label class="authField">
              <span>Своя модель OpenRouter</span>
              <input data-ai-custom-model value="${escapeHtml(aiCustomModel)}" placeholder="Например: openai/gpt-4o-mini" />
            </label>
          ` : `
            <div class="authStatus">Своя модель не используется, пока не выбран режим/модель "Своя модель".</div>
          `}
        </div>
        <p><strong>Фактически будет использована модель:</strong> ${escapeHtml(resolvedModel)}</p>
        <p><strong>Лимит ответа:</strong> ${formatNumberSafe(resolvedMaxTokens)} tokens · <strong>режим:</strong> ${escapeHtml(aiPresetLabel(preset))} · <strong>${escapeHtml(costLabel)}</strong></p>
        <p>${escapeHtml(aiPresetGuidance(aiPreset) || preset?.purpose || 'Своя модель OpenRouter. Проверьте стоимость в кабинете OpenRouter.')}${preset?.warning ? ` ${escapeHtml(preset.warning)}` : ''}</p>
        ${isCustomAiModel() ? '<div class="authStatus">Своя модель разрешена backend-настройками только если OPENROUTER_ALLOW_CUSTOM_MODELS=true. Проверьте стоимость вручную.</div>' : ''}
      </details>
      <div class="heroActions">
        <button class="secondaryButton" type="button" data-test-ai-model ${aiModelTestLoading ? 'disabled' : ''}>${aiModelTestLoading ? 'Проверяем...' : 'Проверить модель'}</button>
      </div>
      ${aiModelTestStatus ? `<div class="authStatus integrationStatus">${escapeHtml(aiModelTestStatus)}</div>` : ''}
    </section>
  `;
}

function renderAiChat() {
  const campaigns = perfSummary?.campaigns || [];
  const quickActions = [
    'Проведи аудит Яндекс.Директа по чеклисту',
    'Найди критичные проблемы',
    'Проанализируй поисковые запросы',
    'Предложи минус-слова с рисками',
    'Разбери вчерашний день',
  ];
  return `
    <section class="panel aiChatPanel">
      <div class="panelHeader">
        <div>
          <h3>Единый AI-чат по клиенту</h3>
          <p>AI получает серверный контекст клиента, кампаний, выбранных целей Директа, сводки эффективности и плана оптимизации. Все действия — только черновики.</p>
        </div>
        <span class="aiStatusBadge ${campaigns.length ? 'ready' : 'pending'}">${campaigns.length ? 'Кампании в контексте' : 'Нет данных sync'}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi blue"><span>Цели</span><strong>${escapeHtml(perfSummary?.selectedGoalIds?.join(', ') || currentClient().conversionGoalIds || currentClient().mainGoalId || '—')}</strong></article>
        <article class="kpi green"><span>Конверсии по целям</span><strong>${perfSummary?.goalConversionsTotal == null ? '—' : formatNumberSafe(perfSummary.goalConversionsTotal)}</strong></article>
        <article class="kpi orange"><span>Кампании</span><strong>${formatNumberSafe(campaigns.length)}</strong></article>
      </div>
      <div class="heroActions">${quickActions.map((text) => `<button class="secondaryButton" type="button" data-ai-quick-action="${escapeHtml(text)}">${escapeHtml(text)}</button>`).join('')}</div>
      <label class="clientSelect">
        <span>Контекст кампании</span>
        <select data-ai-campaign-select>
          <option value="">Весь аккаунт</option>
          ${campaigns.map((campaign) => `<option value="${escapeHtml(campaign.campaign_name)}" ${campaign.campaign_name === selectedAiCampaignName ? 'selected' : ''}>${escapeHtml(campaign.campaign_name)}</option>`).join('')}
        </select>
      </label>
      <div class="aiChatMessages">
        ${aiChatMessages.map((item, index) => `
          <article class="aiChatMessage ${item.role}">
            <strong>${item.role === 'user' ? 'Вы' : 'DirectPilot AI'}</strong>
            <pre>${escapeHtml(item.content)}</pre>
            ${item.source ? `<small>${escapeHtml(item.source)}</small>` : ''}
            ${item.role === 'assistant' ? `<button class="secondaryButton" type="button" data-save-ai-memory="${index}">Сохранить в память проекта</button>` : ''}
          </article>
        `).join('')}
        ${aiChatLoading ? '<article class="aiChatMessage assistant"><strong>DirectPilot AI</strong><pre>Собираю контекст через MCP tools...</pre></article>' : ''}
      </div>
      ${aiChatError ? `<div class="authStatus aiError"><p>${escapeHtml(aiChatError)}</p>${aiChatErrorDetails?.model ? `<p>Модель: ${escapeHtml(aiChatErrorDetails.model)}. Free/custom модели могут часто получать rate limit.</p>` : ''}${aiChatErrorDetails?.retryable ? '<button class="secondaryButton" type="button" data-ai-economy-fallback="chat">Повторить на модели Эконом</button>' : ''}</div>` : ''}
      <form class="aiChatForm" data-ai-chat-form>
        <textarea name="message" rows="3" data-ai-chat-input placeholder="Например: какие кампании дают расход без конверсий и какие цели Метрики проверить?">${escapeHtml(aiChatInput)}</textarea>
        <button class="approveButton" type="submit" ${aiChatLoading ? 'disabled' : ''}>${aiChatLoading ? 'Думаю...' : 'Отправить в AI-чат'}</button>
        <button class="secondaryButton" type="button" data-clear-ai-chat>Очистить чат</button>
      </form>
      ${aiChatToolTraces.length ? `
        <details class="aiToolTrace">
          <summary>Какие MCP-инструменты использовались (${aiChatToolTraces.length})</summary>
          <div>${aiChatToolTraces.map((trace) => `<code>${escapeHtml(trace.name)} ${escapeHtml(JSON.stringify(trace.arguments))}</code>`).join('')}</div>
        </details>
      ` : ''}
    </section>
  `;
}

function renderAiAssistant() {
  const client = currentClient();
  const actionCounts = getOptimizationActionCounts(optimizationActionsByClientId[selectedClientId] || optimizationActions);
  const aiEmptyState = !client.id
    ? { text: 'Сначала создайте клиента.', button: 'Создать клиента', view: 'clients' }
    : !clientYandexIntegration?.connected
      ? { text: 'Привяжите Яндекс-аккаунт к этому клиенту, чтобы AI видел реальные данные.', button: 'Открыть интеграции', view: 'integrations' }
      : !hasPerformanceData()
        ? { text: 'Запустите синхронизацию, чтобы AI увидел кампании.', button: 'Открыть обзор', view: 'dashboard' }
        : !client.conversionGoalIds && !client.mainGoalId
          ? { text: 'Укажите ID целей Метрики для расчёта CPA.', button: 'Открыть клиента', view: 'clients' }
          : null;
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">🧠 AI-аналитик</span>
      <h2>Единое AI workspace по клиенту</h2>
      <p>${client.id ? `Клиент: ${escapeHtml(client.name)}. ${perfSummary?.hasGoalData ? 'AI видит конверсии по выбранным целям Директа.' : 'Загрузите summary и проверьте цели, чтобы AI видел целевые конверсии.'}` : 'Сначала создайте клиента.'}</p>
    </div>
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Как DirectPilot проверяет рекламу</h3>
          <p>Методика идёт от бизнес-контекста к данным, кампаниям, запросам и черновикам действий. Если данных нет, AI должен пометить пункт как «нужны дополнительные данные», а не как ошибку.</p>
        </div>
        <span class="aiStatusBadge ready">Методика включена</span>
      </div>
      <details>
        <summary class="secondaryButton">Методика DirectPilot</summary>
        <ol>
          <li>Контекст бизнеса — ниша, бренд, продукт, гео, целевое действие.</li>
          <li>Посадочные страницы — лендинги, релевантность, путь к конверсии.</li>
          <li>Аналитика — цели, Метрика, выбранные цели Директа.</li>
          <li>Аккаунт Директа — структура, кампании, настройки.</li>
          <li>Кампании — показы, клики, CTR, расход, конверсии по целям, CPA, CR.</li>
          <li>Динамика — сравнение по дням/неделям, поиск ухудшений.</li>
          <li>Поисковые запросы — интент, нерелевантные запросы, минус-слова.</li>
          <li>План действий — критические проблемы, быстрые улучшения, черновики.</li>
        </ol>
        <p>Бизнес-контекст, лендинги, объявления, расширения, настройки аккаунта и недельная динамика пока требуют дополнительных данных.</p>
      </details>
    </section>
    <section class="panel">
      <div class="panelHeader">
        <h3>Контекст анализа</h3>
        <span class="aiStatusBadge ${canRunAiAnalysis() ? 'ready' : 'pending'}">${canRunAiAnalysis() ? 'Данные готовы' : 'Нужна синхронизация'}</span>
      </div>
      <p>Direct: ${escapeHtml(client.directLogin)} · Метрика: ${escapeHtml(client.metricaCounter)} · Цели: ${escapeHtml(perfSummary?.selectedGoalIds?.join(', ') || client.conversionGoalIds || client.mainGoalId || 'не указаны')}</p>
      <p>Бизнес-контекст: ${businessContextFilledCount() ? `${escapeHtml(businessContext?.brandName || client.name)} · ${escapeHtml(businessContext?.businessNiche || 'ниша не указана')} · заполнено ${formatNumberSafe(businessContextFilledCount())} полей` : 'не заполнен — AI не будет выдумывать нишу, сезонность и посадочные.'}</p>
      <p>Согласование: ${formatNumberSafe(actionCounts.total)} черновиков · одобрено ${formatNumberSafe(actionCounts.approved)} · отклонено ${formatNumberSafe(actionCounts.rejected)} · нужны правки ${formatNumberSafe(actionCounts.needs_changes)}.</p>
      <p>${!client.id ? 'Сначала создайте клиента.' : !clientYandexIntegration?.connected ? 'AI сможет анализировать настройки, но для данных нужна привязка Яндекса.' : !hasPerformanceData() ? 'Сначала запустите синхронизацию, чтобы AI увидел кампании.' : !client.conversionGoalIds && !client.mainGoalId ? 'Укажите ID целей Метрики для анализа целевых конверсий.' : 'AI использует сводку, диагностику кампаний и план оптимизации.'}</p>
      ${aiEmptyState ? `<div class="authStatus integrationStatus"><strong>${escapeHtml(aiEmptyState.text)}</strong><div class="heroActions"><button class="approveButton" data-go-view="${escapeHtml(aiEmptyState.view)}">${escapeHtml(aiEmptyState.button)}</button></div></div>` : ''}
    </section>
    ${renderYandexDirectAuditPanel(true)}
    ${renderSyncDiagnosticsPanel(true)}
    ${renderAiModelSettings()}
    ${renderAiChat()}
    ${renderClientAiRecommendations()}
  `);
}

function renderAutopilot() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">🛡️ Автопилот</span><h2>Политики безопасной автоматизации</h2><p>ИИ может действовать только в рамках лимитов клиента и после подтверждения критичных изменений.</p></div>
    <section class="panel autopilotPanel">
      <div class="modeCards">
        <article>Только аудит</article><article>Рекомендации</article><article class="selected">После подтверждения</article><article>Автопилот</article>
      </div>
      <div class="rulesGrid">
        ${autopilotRules.map((rule) => `<div class="rule ${rule.enabled ? 'enabled' : 'disabled'}"><span>${rule.enabled ? '✓' : '×'}</span>${rule.label}</div>`).join('')}
      </div>
      <div class="limitsBox">
        <h3>Лимиты клиента</h3>
        <p>Максимальное изменение ставки: 20% · Изменение дневного бюджета: до 10% · Минимальный период анализа: 14 дней</p>
      </div>
    </section>
  `);
}

function render() {
  activeView = normalizeAppView(activeView);
  const views = {
    landing: renderLanding,
    login: renderLogin,
    dashboard: renderDashboard,
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

['pointerup', 'mouseup', 'click'].forEach((eventName) => {
  app.addEventListener(eventName, (event) => {
    if (isInteractiveActionTarget(event.target)) return;
    const field = getEditableFieldTarget(event.target) || pendingEditableFocusTarget;
    if (!field) return;
    setTimeout(() => {
      if (document.body.contains(field)) {
        field.focus({ preventScroll: true });
      }
    }, 0);
  }, true);
});

app.addEventListener('click', async (event) => {
  const saveApiBaseButton = event.target.closest('[data-save-api-base]');
  if (saveApiBaseButton) {
    event.preventDefault();
    const apiBaseConfig = saveApiBaseButton.closest('[data-api-base-config]');
    const apiBaseInput = apiBaseConfig?.querySelector('[data-api-base-input]');
    const apiBase = String(apiBaseInput?.value || apiBaseDraft).trim().replace(/\/$/, '');
    if (apiBase) {
      localStorage.setItem('directpilot_api_base', apiBase);
    } else {
      localStorage.removeItem('directpilot_api_base');
    }
    window.location.reload();
    return;
  }

  if (isPlainTextInputTarget(event.target) && !isInteractiveActionTarget(event.target)) {
    return;
  }

  const viewButton = getViewActionTarget(event.target);
  const clientButton = event.target.closest('[data-client-id]');
  const integrationButton = event.target.closest('[data-integration]');
  const clientAiButton = event.target.closest('[data-client-ai-recommendations]');
  const syncButton = event.target.closest('[data-sync-client]');
  const summaryButton = event.target.closest('[data-load-summary]');
  const deleteClientButton = event.target.closest('[data-delete-client]');
  const unbindYandexButton = event.target.closest('[data-unbind-yandex]');
  const logoutButton = event.target.closest('[data-logout]');
  const refreshYandexButton = event.target.closest('[data-refresh-yandex-status]');
  const goViewButton = event.target.closest('[data-go-view]');
  const syncJobsButton = event.target.closest('[data-load-sync-jobs]');
  const optimizationPlanButton = event.target.closest('[data-load-optimization-plan]');
  const loadOptimizationActionsButton = event.target.closest('[data-load-optimization-actions]');
  const saveOptimizationActionsButton = event.target.closest('[data-save-optimization-actions]');
  const updateOptimizationActionButton = event.target.closest('[data-update-optimization-action]');
  const executionPreviewButton = event.target.closest('[data-load-execution-preview]');
  const optimizationFilterButton = event.target.closest('[data-optimization-filter]');
  const optimizationActionFilterButton = event.target.closest('[data-optimization-action-filter]');
  const copyOptimizationPlanButton = event.target.closest('[data-copy-optimization-plan]');
  const copyTextButton = event.target.closest('[data-copy-text]');
  const aiQuickActionButton = event.target.closest('[data-ai-quick-action]');
  const aiFallbackButton = event.target.closest('[data-ai-economy-fallback]');
  const testAiModelButton = event.target.closest('[data-test-ai-model]');
  const clearAiChatButton = event.target.closest('[data-clear-ai-chat]');
  const resetBusinessContextButton = event.target.closest('[data-reset-business-context]');
  const saveAiMemoryButton = event.target.closest('[data-save-ai-memory]');

  if (logoutButton) {
    localStorage.removeItem('directpilot_session');
    localStorage.removeItem('directpilot_email');
    window.location.href = 'login.html';
    return;
  }

  if (refreshYandexButton) {
    integrationStatus = {};
    clientYandexIntegration = null;
    clientYandexLoadedFor = '';
    clientYandexStatus = 'Обновляем статус Яндекса...';
    render();
    await loadIntegrationStatus();
    await loadClientYandexIntegration(true);
    render();
    return;
  }

  if (goViewButton) {
    activeView = normalizeAppView(goViewButton.dataset.goView);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    render();
    return;
  }

  if (syncJobsButton) {
    await loadSyncJobs();
    return;
  }

  if (optimizationPlanButton) {
    await loadOptimizationPlan();
    return;
  }

  if (loadOptimizationActionsButton) {
    await loadOptimizationActions();
    return;
  }

  if (saveOptimizationActionsButton) {
    await saveOptimizationPlanAsDrafts();
    return;
  }

  if (updateOptimizationActionButton) {
    const actionId = updateOptimizationActionButton.dataset.updateOptimizationAction;
    const nextStatus = updateOptimizationActionButton.dataset.actionStatus;
    const comment = app.querySelector(`[data-optimization-action-comment="${CSS.escape(actionId)}"]`)?.value || '';
    await updateOptimizationAction(actionId, nextStatus, comment);
    return;
  }

  if (executionPreviewButton) {
    await loadOptimizationExecutionPreview(executionPreviewButton.dataset.loadExecutionPreview);
    return;
  }

  if (optimizationFilterButton) {
    optimizationFilter = optimizationFilterButton.dataset.optimizationFilter;
    render();
    return;
  }

  if (optimizationActionFilterButton) {
    optimizationActionFilter = optimizationActionFilterButton.dataset.optimizationActionFilter || 'all';
    optimizationActionFilterByClientId[selectedClientId] = optimizationActionFilter;
    await loadOptimizationActions();
    return;
  }

  if (copyOptimizationPlanButton) {
    const text = JSON.stringify(optimizationPlan || {}, null, 2);
    await navigator.clipboard?.writeText(text);
    optimizationPlanStatus = 'План скопирован.';
    render();
    return;
  }

  if (copyTextButton) {
    await navigator.clipboard?.writeText(copyTextButton.dataset.copyText || '');
    optimizationPlanStatus = 'Рекомендация скопирована.';
    render();
    return;
  }

  if (aiQuickActionButton) {
    aiChatInput = aiQuickActionButton.dataset.aiQuickAction || '';
    await requestAiChatAnswer();
    return;
  }

  if (aiFallbackButton) {
    const fallbackType = aiFallbackButton.dataset.aiEconomyFallback || lastAiAction?.type;
    applyEconomyFallback();
    aiChatError = '';
    aiChatErrorDetails = null;
    clientAiError = '';
    if (fallbackType === 'recommendations') {
      await requestClientAiRecommendations();
    } else if (lastAiAction?.message) {
      aiChatInput = lastAiAction.message;
      await requestAiChatAnswer();
    } else {
      render();
    }
    return;
  }

  if (testAiModelButton) {
    await testSelectedAiModel();
    return;
  }

  if (clearAiChatButton) {
    aiChatMessages = [{ ...initialAiChatMessage }];
    aiChatInput = '';
    aiChatToolTraces = [];
    aiChatError = '';
    aiChatErrorDetails = null;
    saveActiveAiState();
    render();
    return;
  }

  if (resetBusinessContextButton) {
    render();
    return;
  }

  if (saveAiMemoryButton) {
    const index = Number(saveAiMemoryButton.dataset.saveAiMemory);
    await saveAiMessageToProjectMemory(aiChatMessages[index]?.content || '');
    return;
  }

  if (deleteClientButton) {
    const clientId = deleteClientButton.dataset.deleteClient;
    if (!clientId || !confirm('Удалить клиента? История синхронизаций по нему будет удалена.')) return;
    try {
      if (backendClientsAvailable) {
        await deleteClientOnApi(clientId);
      } else {
        accountClients = accountClients.filter((item) => item.id !== clientId);
        saveAccountClients();
      }
      selectedClientId = accountClients.find((item) => item.id !== clientId)?.id || '';
      saveSelectedClientId();
      resetClientDerivedState();
      resetSelectedClientOperationalState();
      clientsLoaded = false;
      clientFormStatus = 'Клиент удалён.';
      await loadClientsFromApi();
      render();
    } catch (error) {
      clientFormStatus = `Ошибка удаления клиента: ${error.message}`;
      render();
    }
    return;
  }

  if (unbindYandexButton) {
    await unbindClientYandexAccount();
    return;
  }

  if (syncButton) {
    await runClientSync();
    return;
  }

  if (summaryButton) {
    await loadPerformanceSummary();
    return;
  }

  if (clientAiButton) {
    await requestClientAiRecommendations();
    return;
  }

  if (integrationButton) {
    const integration = integrationButton.dataset.integration;
    if (integration === 'yandex-direct' || integration === 'yandex-metrica') {
      integrationButton.disabled = true;
      integrationButton.textContent = 'Открываем OAuth...';
      try {
        await connectYandexIntegration();
      } catch (error) {
        integrationStatus = { message: error.message };
        render();
      }
    } else {
      integrationStatus = { message: 'CRM-интеграция добавлена в план разработки.' };
      render();
    }
    return;
  }

  if (viewButton) {
    activeView = normalizeAppView(viewButton.dataset.view);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    render();
  }

  if (clientButton) {
    saveActiveAiState();
    selectedClientId = clientButton.dataset.clientId;
    saveSelectedClientId();
    clientAiRecommendations = null;
    resetClientDerivedState();
    resetSelectedClientOperationalState();
    clientFormStatus = '';
    activeView = 'dashboard';
    render();
  }
});

app.addEventListener('submit', async (event) => {
  const businessContextForm = event.target.closest('[data-business-context-form]');
  if (businessContextForm) {
    event.preventDefault();
    await saveBusinessContextFromForm(businessContextForm);
    return;
  }

  const settingsForm = event.target.closest('[data-client-settings-form]');
  if (settingsForm) {
    event.preventDefault();
    if (!selectedClientId) return;
    const formData = new FormData(settingsForm);
    const targetCpaValue = String(formData.get('targetCpa') || '').trim();
    const conversionGoalIdsValue = String(formData.get('conversionGoalIds') || '').trim();
    const fallbackMainGoalId = conversionGoalIdsValue.split(/[,\s]+/).filter(Boolean)[0] || '';
    const payload = {
      name: String(formData.get('name') || '').trim(),
      direct_login: String(formData.get('directLogin') || '').trim() || null,
      metrica_counter: String(formData.get('metricaCounter') || '').trim() || null,
      yandex_account_id: currentClient().yandexAccountId || null,
      target_cpa: targetCpaValue ? Number(targetCpaValue) : null,
      main_goal_id: String(formData.get('mainGoalId') || '').trim() || fallbackMainGoalId || null,
      conversion_goal_ids: conversionGoalIdsValue || String(formData.get('mainGoalId') || '').trim() || null,
      notes: String(formData.get('notes') || '').trim() || null,
      segment: currentClient().segment || 'Клиент',
    };
    try {
      const savedClient = await updateClientOnApi(selectedClientId, payload);
      accountClients = accountClients.map((item) => (item.id === savedClient.id ? savedClient : item));
      saveAccountClients();
      optimizationPlanByClientId[selectedClientId] = null;
      resetSelectedClientOperationalState();
      clientFormStatus = 'Настройки клиента сохранены.';
    } catch (error) {
      clientFormStatus = `Ошибка сохранения настроек: ${error.message}`;
    }
    render();
    return;
  }

  const yandexBindForm = event.target.closest('[data-yandex-bind-form]');
  if (yandexBindForm) {
    event.preventDefault();
    const formData = new FormData(yandexBindForm);
    await bindClientYandexAccount(String(formData.get('yandexAccountId') || ''));
    return;
  }

  const clientForm = event.target.closest('[data-client-form]');
  if (clientForm) {
    event.preventDefault();
    const formData = new FormData(clientForm);
    const name = String(formData.get('name') || clientDraftName).trim();
    if (!name) return;
    const directLogin = String(formData.get('directLogin') || clientDraftDirectLogin).trim() || 'Не подключен';
    const metricaCounter = String(formData.get('metricaCounter') || clientDraftMetricaCounter).trim() || 'Не подключен';
    const client = {
      id: makeClientId(name),
      name,
      segment: 'Клиент',
      spend: '—',
      leads: 0,
      cpa: '—',
      roas: '—',
      trend: 'Ожидает синхронизации',
      score: 0,
      status: 'Ожидает подключения данных',
      directLogin,
      metricaCounter,
      yandexAccountId: null,
      targetCpa: null,
      mainGoalId: null,
      conversionGoalIds: null,
      notes: null,
    };
    try {
      if (backendClientsAvailable) {
        const savedClient = await createClientOnApi(client);
        accountClients = [savedClient, ...accountClients.filter((item) => item.id !== savedClient.id)];
        selectedClientId = savedClient.id;
        saveSelectedClientId();
        saveAccountClients();
        resetClientDerivedState();
        resetSelectedClientOperationalState();
        clientFormStatus = 'Клиент сохранён в backend.';
        clientDraftName = '';
        clientDraftDirectLogin = '';
        clientDraftMetricaCounter = '';
        clientForm.reset();
      } else {
        accountClients = [client, ...accountClients.filter((item) => item.id !== client.id)];
        selectedClientId = client.id;
        saveSelectedClientId();
        saveAccountClients();
        resetClientDerivedState();
        resetSelectedClientOperationalState();
        clientFormStatus = 'Backend недоступен: клиент сохранён локально (локальный режим).';
        clientDraftName = '';
        clientDraftDirectLogin = '';
        clientDraftMetricaCounter = '';
        clientForm.reset();
      }
    } catch (error) {
      clientFormStatus = `Ошибка сохранения в backend: ${error.message}`;
    }
    render();
    return;
  }

  const aiChatForm = event.target.closest('[data-ai-chat-form]');
  if (aiChatForm) {
    event.preventDefault();
    const formData = new FormData(aiChatForm);
    aiChatInput = String(formData.get('message') || '').trim();
    await requestAiChatAnswer();
    return;
  }

  const aiForm = event.target.closest('[data-ai-form]');
  if (aiForm) {
    event.preventDefault();
    const formData = new FormData(aiForm);
    const modelMode = String(formData.get('modelMode') || aiModel);
    if (modelMode === CUSTOM_MODEL_VALUE) {
      aiCustomModel = String(formData.get('customModel') || aiCustomModel).trim();
      aiModel = aiCustomModel;
    } else {
      aiModel = modelMode;
    }
    aiPrompt = String(formData.get('prompt') || '').trim();
    await requestAiInsight();
    return;
  }

  const form = event.target.closest('[data-auth-form]');
  if (!form) return;
  event.preventDefault();
  const formData = new FormData(form);
  const email = String(formData.get('email') || '').trim();
  const code = String(formData.get('code') || '').trim();
  authEmail = email;
  authCode = code;
  authLoading = true;
  authStatus = 'Отправляем запрос...';
  render();
  try {
    if (authStep === 'email') {
      const result = await requestEmailCode(email);
      authStep = 'code';
      devCode = result.dev_code;
      authStatus = 'Код отправлен на почту. Проверьте входящие и спам.' + (result.dev_code ? ' Dev code доступен ниже.' : '');
    } else {
      const result = await verifyEmailCode(email, code);
      localStorage.setItem('directpilot_session', result.session_token);
      localStorage.setItem('directpilot_email', result.email);
      window.location.href = 'app.html';
      return;
    }
  } catch (error) {
    authStatus = `${error.message}. Проверьте DATABASE_URL и EMAIL_AUTH_DEV_MODE=true для MVP-режима.`;
  } finally {
    authLoading = false;
  }
  render();
});

app.addEventListener('input', (event) => {
  if (event.target.matches('[data-api-base-input]')) {
    apiBaseDraft = event.target.value;
  }
  if (event.target.matches('input[name="email"]')) {
    authEmail = event.target.value;
  }
  if (event.target.matches('input[name="code"]')) {
    authCode = event.target.value;
  }
  if (event.target.matches('[data-ai-prompt]')) {
    aiPrompt = event.target.value;
  }
  if (event.target.matches('[data-ai-custom-model]')) {
    aiCustomModel = event.target.value;
    aiModel = aiCustomModel;
    saveAiModelSettings();
  }
  if (event.target.matches('[data-ai-chat-input]')) {
    aiChatInput = event.target.value;
  }
  if (event.target.matches('[data-client-form] input[name="name"]')) {
    clientDraftName = event.target.value;
  }
  if (event.target.matches('[data-client-form] input[name="directLogin"]')) {
    clientDraftDirectLogin = event.target.value;
  }
  if (event.target.matches('[data-client-form] input[name="metricaCounter"]')) {
    clientDraftMetricaCounter = event.target.value;
  }
});

app.addEventListener('change', (event) => {
  if (event.target.matches('[data-client-select]')) {
    saveActiveAiState();
    selectedClientId = event.target.value;
    saveSelectedClientId();
    resetClientDerivedState();
    resetSelectedClientOperationalState();
    clientFormStatus = '';
    render();
  }
  if (event.target.matches('[data-ai-campaign-select]')) {
    selectedAiCampaignName = event.target.value;
    saveActiveAiState();
    render();
  }
  if (event.target.matches('[data-ai-model]')) {
    if (event.target.value === CUSTOM_MODEL_VALUE) {
      aiModel = aiCustomModel;
      aiPreset = 'custom';
    } else {
      aiModel = event.target.value;
      if (aiPreset === 'custom') aiPreset = aiStatus.recommended_default_preset || 'economy';
    }
    saveAiModelSettings();
    render();
  }
  if (event.target.matches('[data-ai-preset]')) {
    aiPreset = event.target.value;
    if (aiPreset === 'custom') {
      aiModel = aiCustomModel;
    } else {
      const preset = activeAiPresetInfo();
      aiModel = preset.default_model || aiStatus.recommended_default_model || aiStatus.default_model || aiModel;
    }
    saveAiModelSettings();
    render();
  }
  if (event.target.matches('[data-ai-max-tokens-mode]')) {
    aiMaxTokensMode = event.target.value;
    saveAiModelSettings();
    render();
  }
});

render();

if (page === 'app' && (oauthReturnStatus || appQueryParams.get('view'))) {
  window.history.replaceState({}, document.title, window.location.pathname);
  if (activeView === 'integrations' && oauthReturnStatus) {
    integrationStatus = {};
    clientYandexIntegration = null;
    clientYandexLoadedFor = '';
    loadIntegrationStatus();
    loadClientYandexIntegration(true);
  }
}

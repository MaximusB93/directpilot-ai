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
const API_BASE = resolveApiBase();
const page = document.body.dataset.page ?? 'landing';

function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');
  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000/api/v1';
  }
  return `${origin}/api/v1`;
}

function hasCustomApiBase() {
  return Boolean(window.localStorage.getItem('directpilot_api_base')?.trim());
}

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'clients', label: 'Клиенты', icon: '👥' },
  { id: 'audit', label: 'AI-аудит', icon: '⚡' },
  { id: 'recommendations', label: 'Рекомендации', icon: '✨' },
  { id: 'ai', label: 'AI-модели', icon: '🧠' },
  { id: 'reports', label: 'Отчёты', icon: '📄' },
  { id: 'autopilot', label: 'Автопилот', icon: '🛡️' },
  { id: 'integrations', label: 'Интеграции', icon: '🔌' },
];

let activeView = page === 'login' ? 'login' : page === 'app' ? 'dashboard' : 'landing';
let authEmail = '';
let authStatus = '';
let authStep = 'email';
let authCode = '';
let authLoading = false;
let devCode = null;
let integrationStatus = {};
let accountClients = loadAccountClients();
let aiStatus = { models: [], configured: false, message: 'Статус OpenRouter ещё не загружен.' };
const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';
let aiModel = 'openrouter/auto';
let aiCustomModel = 'openai/gpt-4o';
let aiPrompt = 'Проанализируй выбранного клиента DirectPilot AI: какие данные нужны из Яндекс.Директа и Метрики, чтобы сформировать первые рекомендации?';
let aiResponse = null;
let aiError = '';
let aiLoading = false;
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
let clientsLoaded = false;
let backendClientsAvailable = false;
let backendClientsStatus = 'Проверяем подключение backend...';
let aiChatMessages = [
  { role: 'assistant', content: 'Здравствуйте! Я AI-аналитик DirectPilot. Спросите про Директ, Метрику, CPA, цели или рекомендации — я соберу данные через MCP-инструменты и отвечу по контексту.' },
];
let aiChatInput = 'Почему растёт CPA и что проверить в Яндекс.Метрике?';
let aiChatLoading = false;
let aiChatError = '';
let aiChatToolTraces = [];

let selectedClientId = window.localStorage.getItem('directpilot_selected_client_id') || accountClients[0]?.id || '';




function saveSelectedClientId() {
  if (selectedClientId) {
    localStorage.setItem('directpilot_selected_client_id', selectedClientId);
  }
}

async function loadClientsFromApi() {
  if (clientsLoaded) return;
  clientsLoaded = true;
  try {
    const response = await fetch(`${API_BASE}/clients`);
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
    saveAccountClients();
    render();
  } catch (error) {
    backendClientsAvailable = false;
    backendClientsStatus = 'Backend недоступен. Включён demo/fallback режим (данные из localStorage).';
    accountClients = loadAccountClients();
    if (!selectedClientId || !accountClients.some((client) => client.id === selectedClientId)) {
      selectedClientId = accountClients[0]?.id || '';
    }
    saveSelectedClientId();
    render();
  }
}

async function createClientOnApi(client) {
  const response = await fetch(`${API_BASE}/clients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id: client.id,
      name: client.name,
      direct_login: client.directLogin === 'Не подключен' ? null : client.directLogin,
      metrica_counter: client.metricaCounter === 'Не подключен' ? null : client.metricaCounter,
      segment: client.segment,
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось сохранить клиента в базе данных');
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
    const saved = JSON.parse(localStorage.getItem('directpilot_clients') || '[]');
    return Array.isArray(saved) ? saved : initialClients;
  } catch (error) {
    return initialClients;
  }
}

function saveAccountClients() {
  localStorage.setItem('directpilot_clients', JSON.stringify(accountClients));
}

function isEditingTextField() {
  const element = document.activeElement;
  return Boolean(element?.matches?.('input, textarea, select'));
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

function currentClient() {
  return accountClients.find((client) => client.id === selectedClientId) ?? accountClients[0] ?? emptyClient();
}

function resetClientDerivedState() {
  clientAiRecommendations = null;
  clientAiError = '';
  aiChatToolTraces = [];
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
  const githubPagesWarning = window.location.hostname === 'maximusb93.github.io' && !hasCustomApiBase()
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
      <form class="authForm" data-api-base-form>
        <div class="authField">
          <label for="backend-api-base">Backend API URL</label>
          <input id="backend-api-base" type="url" name="apiBase" value="${escapeHtml(API_BASE)}" placeholder="https://your-backend.vercel.app/api/v1" autocomplete="url" required />
        </div>
        <button class="secondaryButton" type="submit">Сохранить backend URL</button>
      </form>
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
  const response = await fetch(`${API_BASE}/auth/yandex/start`);
  const payload = await response.json();
  if (!response.ok || !payload.auth_url) throw new Error(payload.detail || payload.message || 'OAuth URL не получен');
  window.location.href = payload.auth_url;
}

async function loadAiStatus() {
  try {
    const response = await fetch(`${API_BASE}/ai/openrouter/status`);
    aiStatus = response.ok ? await response.json() : { models: [], configured: false, message: 'Не удалось получить статус OpenRouter.' };
    aiModel = aiStatus.default_model || aiStatus.models?.[0]?.id || aiModel;
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
    const response = await fetch(`${API_BASE}/ai/openrouter/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: activeAiModel(), prompt: aiPrompt }),
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



async function requestAiChatAnswer() {
  if (!selectedClientId) {
    aiChatError = 'Сначала добавьте клиента: чат анализирует данные в контексте выбранного клиента.';
    render();
    return;
  }
  const message = aiChatInput.trim();
  if (!message) return;
  const history = aiChatMessages.slice(-8);
  aiChatMessages = [...aiChatMessages, { role: 'user', content: message }];
  aiChatInput = '';
  aiChatLoading = true;
  aiChatError = '';
  aiChatToolTraces = [];
  render();
  try {
    const response = await fetch(`${API_BASE}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: selectedClientId, model: activeAiModel(), message, history, client_context: currentClient() }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'AI-чат не вернул ответ');
    aiChatMessages = [...aiChatMessages, { role: 'assistant', content: payload.answer, source: payload.source }];
    aiChatToolTraces = payload.tool_traces || [];
  } catch (error) {
    aiChatError = error.message;
  } finally {
    aiChatLoading = false;
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
  render();
  try {
    const response = await fetch(`${API_BASE}/clients/${selectedClientId}/ai/recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: activeAiModel(), client_context: currentClient() }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось сформировать AI-рекомендации');
    clientAiRecommendations = payload;
  } catch (error) {
    clientAiError = error.message;
  } finally {
    clientAiLoading = false;
    render();
  }
}

async function loadIntegrationStatus() {
  try {
    const response = await fetch(`${API_BASE}/auth/yandex/status`);
    integrationStatus = response.ok ? await response.json() : {};
    if (activeView === 'integrations') render();
  } catch (error) {
    integrationStatus = { message: 'Не удалось получить статус интеграций' };
  }
}



async function runClientSync() {
  if (!selectedClientId) return;
  syncLoading = true;
  syncStatusMessage = 'Запускаем синхронизацию...';
  render();
  try {
    const response = await fetch(`${API_BASE}/clients/${selectedClientId}/sync`, { method: 'POST' });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Ошибка синхронизации');
    if (payload.rows_loaded === 0 && (payload.status === 'failed' || payload.status === 'no_data' || payload.status === 'success')) {
      syncStatusMessage = 'Данные не загружены: подключите Яндекс.Директ или проверьте выбранный период.';
    } else {
      syncStatusMessage = `Синхронизация: ${payload.status}, строк: ${payload.rows_loaded}, источник: ${payload.source_type}`;
    }
    clientsLoaded = false;
    await loadClientsFromApi();
  } catch (error) {
    syncStatusMessage = `Ошибка синхронизации: ${error.message}`;
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
    const response = await fetch(`${API_BASE}/clients/${selectedClientId}/performance-summary`);
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
          <p>Добавляйте клиентов отдельно и подключайте для каждого Яндекс.Директ и Метрику.</p>
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
        ${content}
      </section>
    </div>
  `;
}

function renderDashboard() {
  const client = currentClient();
  const hasClient = Boolean(client.id);
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">📊 Agency overview</span>
      <h2>Центр управления рекламой и AI-рекомендациями</h2>
      <p>${hasClient ? 'Сводка по выбранному клиенту, источникам данных и действиям, которые ИИ сможет предложить после загрузки статистики.' : 'В личном кабинете больше нет предзагруженных демо-данных. Добавьте первого клиента и подключите его аккаунты.'}</p>
      <div class="heroActions">
        <button class="approveButton" data-sync-client ${!hasClient || syncLoading ? 'disabled' : ''}>${syncLoading ? 'Синхронизация...' : 'Запустить синхронизацию'}</button>
        <button class="secondaryButton" data-load-summary ${!hasClient || perfLoading ? 'disabled' : ''}>${perfLoading ? 'Загружаем...' : 'Показать сводку'}</button>
      </div>
      ${syncStatusMessage ? `<div class="authStatus integrationStatus">${escapeHtml(syncStatusMessage)}</div>` : ''}
    </div>
    <div class="metricGrid">${agencyMetrics.map(metricCard).join('')}</div>
    ${!hasClient ? `
      <section class="panel emptyStatePanel">
        <h3>Добавьте первого клиента</h3>
        <p>Каждый клиент хранится отдельно: название проекта, логин Яндекс.Директа и счётчик Метрики. После подключения источников здесь появятся кампании, цели, CPA и рекомендации.</p>
        <button class="approveButton" data-view="clients">Перейти к клиентам</button>
      </section>
    ` : `
      <div class="dashboardLayout">
        <section class="panel scorePanel">
          <div class="scoreRing" style="--score: ${client.score}%"><strong>${client.score}</strong><span>/100</span></div>
          <div>
            <span class="muted">AI score аккаунта</span>
            <h3>${client.status}</h3>
            <p>Оценка появится после синхронизации Директа, Метрики и минимального периода анализа.</p>
          </div>
        </section>
        <section class="panel">
          <div class="panelHeader"><h3>Что сделать сегодня</h3><button data-view="integrations">Подключить источники</button></div>
          <div class="taskList">
            <article><strong>Подключить Яндекс.Директ</strong><span>Источник расходов</span><p>${client.directLogin}</p></article>
            <article><strong>Подключить Яндекс.Метрику</strong><span>Источник целей</span><p>${client.metricaCounter}</p></article>
            <article><strong>Запустить AI-анализ</strong><span>После синхронизации</span><p>Рекомендации строятся только по данным клиента.</p></article>
          </div>
        </section>
      </div>
      <section class="panel">
        <div class="panelHeader"><h3>Кампании клиента</h3><button data-view="integrations">Проверить подключение</button></div>
        ${campaigns.length ? `
          <div class="tableWrap">
            <table>
              <thead><tr><th>Кампания</th><th>Расход</th><th>Лиды</th><th>CPA</th><th>Статус</th></tr></thead>
              <tbody>${campaigns.map((campaign) => `<tr><td>${campaign.name}</td><td>${campaign.spend}</td><td>${campaign.leads}</td><td>${campaign.cpa}</td><td><span class="tableStatus">${campaign.status}</span></td></tr>`).join('')}</tbody>
            </table>
          </div>
        ` : `<div class="emptyStatePanel compact"><h3>Кампании ещё не загружены</h3><p>Подключите OAuth Яндекса и выберите логин клиента, чтобы загрузить реальные кампании из Direct API.</p></div>`}
      </section>
    `}
    ${perfSummary ? `
      <section class="panel">
        <h3>Сводка эффективности (${escapeHtml(perfSummary.message)})</h3>
        <p>Расход: ${perfSummary.totals.cost} ₽ · Показы: ${perfSummary.totals.impressions} · Клики: ${perfSummary.totals.clicks} · Конверсии: ${perfSummary.totals.conversions}</p>
        <p>Avg CPC: ${perfSummary.totals.avg_cpc} · CPA: ${perfSummary.totals.cpa ?? '—'}</p>
      </section>
    ` : ''}
  `);
}

function renderClients() {
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
        <p>Расход: ${perfSummary.totals.cost} ₽ · Показы: ${perfSummary.totals.impressions} · Клики: ${perfSummary.totals.clicks} · Конверсии: ${perfSummary.totals.conversions}</p>
        <p>Avg CPC: ${perfSummary.totals.avg_cpc} · CPA: ${perfSummary.totals.cpa ?? '—'}</p>
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
    return `<section class="panel aiDraftPanel"><h3>AI-рекомендации недоступны</h3><p>${escapeHtml(clientAiError)}</p></section>`;
  }
  if (!clientAiRecommendations) return '';
  return `
    <section class="panel aiDraftPanel">
      <div class="panelHeader">
        <div>
          <h3>AI-черновик по контексту клиента</h3>
          <p>${escapeHtml(clientAiRecommendations.summary)}</p>
        </div>
        <span class="aiStatusBadge ready">${escapeHtml(clientAiRecommendations.source)}</span>
      </div>
      <div class="aiDraftGrid">
        ${clientAiRecommendations.recommendations.map((item) => `
          <article>
            <div class="actionTop"><span>${escapeHtml(item.risk)} риск</span><strong>${item.requires_approval ? 'Approval' : 'Read-only'}</strong></div>
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
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">✨ Рекомендации</span><h2>Действия с объяснениями и контролем риска</h2><p>В production каждая карточка будет иметь dry-run, diff, approval и rollback-данные.</p></div>
    <section class="panel aiRecommendationCta">
      <div>
        <h3>Сформировать AI-рекомендации по клиентскому контексту</h3>
        <p>Backend соберёт профиль клиента, кампании, аудит, текущие рекомендации и guardrails, а затем вернёт структурированный черновик. Если OpenRouter не настроен, покажем безопасный fallback.</p>
      </div>
      <button class="approveButton" data-client-ai-recommendations ${clientAiLoading ? 'disabled' : ''}>${clientAiLoading ? 'Генерируем...' : 'Сгенерировать AI-черновик'}</button>
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
            <div class="actionButtons"><button>Подробнее</button><button class="approveButton">Применить после подтверждения</button></div>
          </article>
        `).join('')}
      </div>
    ` : `<section class="panel emptyStatePanel compact"><h3>Рекомендаций пока нет</h3><p>Нажмите «Сгенерировать AI-черновик» после добавления клиента или подключите реальные источники данных.</p></section>`}
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
  const connected = integrationStatus.connected;
  const account = integrationStatus.accounts?.[0];
  const statusText = connected ? `Подключено: ${account.login}` : 'Не подключено';
  const client = currentClient();
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
        <div class="integrationTop"><span>Яндекс.Директ</span><strong>${statusText}</strong></div>
        <h3>Рекламные кампании и отчёты</h3>
        <p>Подключение уже работает: backend получает OAuth token, хранит его в Postgres и читает кампании/отчёты Direct API.</p>
        <code>GET /api/v1/auth/yandex/start</code>
        <button class="approveButton" data-integration="yandex-direct">${connected ? 'Переподключить Директ' : 'Подключить Яндекс.Директ'}</button>
      </article>
      <article class="integrationCard primaryIntegration">
        <div class="integrationTop"><span>Яндекс.Метрика</span><strong>${connected ? 'Доступ выдан' : 'Требуется OAuth'}</strong></div>
        <h3>Цели, конверсии и ecommerce</h3>
        <p>Используем тот же OAuth-flow со scope metrika:read. Следующий backend-шаг — чтение счётчиков и целей Метрики.</p>
        <code>scope: metrika:read</code>
        <button class="approveButton" data-integration="yandex-metrica">${connected ? 'Обновить доступ Метрики' : 'Подключить Яндекс.Метрику'}</button>
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

function renderAiChat() {
  return `
    <section class="panel aiChatPanel">
      <div class="panelHeader">
        <div>
          <h3>AI-чат с MCP-инструментами</h3>
          <p>Чат отвечает на вопросы пользователя, собирая контекст через MCP tools: клиенты, кампании Директа, цели Метрики, аудит и рекомендации.</p>
        </div>
        <span class="aiStatusBadge ready">MCP tools</span>
      </div>
      <div class="aiChatMessages">
        ${aiChatMessages.map((item) => `
          <article class="aiChatMessage ${item.role}">
            <strong>${item.role === 'user' ? 'Вы' : 'DirectPilot AI'}</strong>
            <pre>${escapeHtml(item.content)}</pre>
            ${item.source ? `<small>${escapeHtml(item.source)}</small>` : ''}
          </article>
        `).join('')}
        ${aiChatLoading ? '<article class="aiChatMessage assistant"><strong>DirectPilot AI</strong><pre>Собираю контекст через MCP tools...</pre></article>' : ''}
      </div>
      ${aiChatError ? `<div class="authStatus aiError">${escapeHtml(aiChatError)}</div>` : ''}
      <form class="aiChatForm" data-ai-chat-form>
        <textarea name="message" rows="3" data-ai-chat-input placeholder="Например: какие кампании дают расход без конверсий и какие цели Метрики проверить?">${escapeHtml(aiChatInput)}</textarea>
        <button class="approveButton" type="submit" ${aiChatLoading ? 'disabled' : ''}>${aiChatLoading ? 'Думаю...' : 'Отправить в AI-чат'}</button>
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
  const models = aiStatus.models?.length ? aiStatus.models : [{ id: aiModel, name: aiModel, description: 'Модель будет загружена из backend.' }];
  const customSelected = isCustomAiModel();
  const customAllowed = aiStatus.allow_custom_models !== false;
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">🧠 OpenRouter</span>
      <h2>AI-слой с выбором модели</h2>
      <p>Ключ OpenRouter хранится только на backend. Интерфейс отправляет задачу в наш API, выбирает модель и показывает ответ как черновик для специалиста.</p>
    </div>
    ${renderAiChat()}
    <div class="aiGrid">
      <section class="panel aiConsole">
        <div class="panelHeader">
          <h3>Запрос к AI</h3>
          <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'OpenRouter готов' : 'Нужен API key'}</span>
        </div>
        <form class="aiForm" data-ai-form>
          <label>
            <span>Модель</span>
            <select name="modelMode" data-ai-model>
              ${models.map((model) => `<option value="${model.id}" ${model.id === aiModel && !customSelected ? 'selected' : ''}>${model.name}</option>`).join('')}
              <option value="${CUSTOM_MODEL_VALUE}" ${customSelected ? 'selected' : ''} ${customAllowed ? '' : 'disabled'}>Ввести модель вручную</option>
            </select>
          </label>
          ${customSelected ? `
            <label>
              <span>Своя модель OpenRouter</span>
              <input name="customModel" data-ai-custom-model placeholder="openai/gpt-4o" value="${escapeHtml(aiCustomModel)}" autocomplete="off" />
              <small>Введите точный id модели из OpenRouter, например <code>openai/gpt-4o</code> или <code>anthropic/claude-3.5-sonnet</code>.</small>
            </label>
          ` : ''}
          <label>
            <span>Задача для AI</span>
            <textarea name="prompt" rows="7" maxlength="4000" data-ai-prompt>${escapeHtml(aiPrompt)}</textarea>
          </label>
          <button class="approveButton" type="submit" ${aiLoading || !aiStatus.configured ? 'disabled' : ''}>${aiLoading ? 'Генерируем...' : 'Получить AI-рекомендацию'}</button>
        </form>
        <div class="authStatus integrationStatus">${escapeHtml(aiStatus.message || 'Статус неизвестен')}</div>
        ${aiError ? `<div class="authStatus aiError">${escapeHtml(aiError)}</div>` : ''}
        ${aiResponse ? `
          <article class="aiResponse">
            <div class="integrationTop"><span>Ответ модели</span><strong>${escapeHtml(aiResponse.model)}</strong></div>
            <pre>${escapeHtml(aiResponse.content)}</pre>
          </article>
        ` : ''}
      </section>
      <aside class="aiSide">
        <article class="integrationCard primaryIntegration">
          <div class="integrationTop"><span>Контекст</span><strong>${escapeHtml(client.name)}</strong></div>
          <h3>Что отдаём модели</h3>
          <p>На старте отправляем только текстовую задачу и безопасный системный промпт. Следующий шаг — добавлять нормализованные KPI, аудит, рекомендации и approval-историю.</p>
        </article>
        <article class="integrationCard">
          <div class="integrationTop"><span>Подход</span><strong>RAG + guardrails</strong></div>
          <h3>Как использовать ИИ правильно</h3>
          <p>Не «обучаем» модель на первом этапе. Сначала даём ей качественный контекст, схемы данных, проверяемые метрики и запрещаем применять изменения без dry-run и подтверждения.</p>
        </article>
        <article class="integrationCard">
          <div class="integrationTop"><span>Модели</span><strong>${models.length}</strong></div>
          <h3>Разные модели под разные задачи</h3>
          <p>Быстрые модели — для сводок и черновиков. Более сильные — для стратегического анализа, сложных причинно-следственных выводов и ревью рекомендаций.</p>
        </article>
      </aside>
    </div>
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
  const views = {
    landing: renderLanding,
    login: renderLogin,
    dashboard: renderDashboard,
    clients: renderClients,
    audit: renderAudit,
    recommendations: renderRecommendations,
    ai: renderAiAssistant,
    reports: renderReports,
    autopilot: renderAutopilot,
    integrations: renderIntegrations,
  };
  app.innerHTML = views[activeView]();
  document.body.dataset.view = activeView;
  if (activeView === 'login') {
    const emailInput = app.querySelector('input[name="email"]');
    if (emailInput) emailInput.value = authEmail;
  }
  if (activeView === 'integrations' && !integrationStatus.message && integrationStatus.connected === undefined) {
    loadIntegrationStatus();
  }
  if (activeView === 'ai' && aiStatus.message === 'Статус OpenRouter ещё не загружен.') {
    loadAiStatus();
  }
  if (activeView !== 'landing' && activeView !== 'login') {
    loadClientsFromApi();
  }
}

app.addEventListener('click', async (event) => {
  const viewButton = event.target.closest('[data-view]');
  const clientButton = event.target.closest('[data-client-id]');
  const integrationButton = event.target.closest('[data-integration]');
  const clientAiButton = event.target.closest('[data-client-ai-recommendations]');
  const syncButton = event.target.closest('[data-sync-client]');
  const summaryButton = event.target.closest('[data-load-summary]');

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
    activeView = viewButton.dataset.view;
    window.scrollTo({ top: 0, behavior: 'smooth' });
    render();
  }

  if (clientButton) {
    selectedClientId = clientButton.dataset.clientId;
    saveSelectedClientId();
    clientAiRecommendations = null;
    resetClientDerivedState();
    clientFormStatus = '';
    activeView = 'dashboard';
    render();
  }
});

app.addEventListener('submit', async (event) => {
  const apiBaseForm = event.target.closest('[data-api-base-form]');
  if (apiBaseForm) {
    event.preventDefault();
    const formData = new FormData(apiBaseForm);
    const apiBase = String(formData.get('apiBase') || '').trim().replace(/\/$/, '');
    if (apiBase) {
      localStorage.setItem('directpilot_api_base', apiBase);
    } else {
      localStorage.removeItem('directpilot_api_base');
    }
    window.location.reload();
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
    };
    try {
      if (backendClientsAvailable) {
        const savedClient = await createClientOnApi(client);
        accountClients = [savedClient, ...accountClients.filter((item) => item.id !== savedClient.id)];
        selectedClientId = savedClient.id;
        saveSelectedClientId();
        saveAccountClients();
        resetClientDerivedState();
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
    selectedClientId = event.target.value;
    saveSelectedClientId();
    resetClientDerivedState();
    clientFormStatus = '';
    render();
  }
  if (event.target.matches('[data-ai-model]')) {
    if (event.target.value === CUSTOM_MODEL_VALUE) {
      aiModel = aiCustomModel;
    } else {
      aiModel = event.target.value;
    }
    render();
  }
});

render();

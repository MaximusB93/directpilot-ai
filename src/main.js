import {
  agencyMetrics,
  auditIssues,
  autopilotRules,
  campaigns,
  clients,
  recommendations,
  reportBullets,
} from './data.js';

const app = document.querySelector('#app');
const API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
const page = document.body.dataset.page ?? 'landing';
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
let devCode = null;
let integrationStatus = {};
let aiStatus = { models: [], configured: false, message: 'Статус OpenRouter ещё не загружен.' };
let aiModel = 'openrouter/auto';
let aiPrompt = 'Проанализируй демо-клиента DirectPilot AI: какие 3 действия стоит выполнить в Яндекс.Директе на этой неделе и какие данные нужно проверить перед применением?';
let aiResponse = null;
let aiError = '';
let aiLoading = false;

let selectedClientId = clients[0].id;

function currentClient() {
  return clients.find((client) => client.id === selectedClientId) ?? clients[0];
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
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
            <input id="login-email" type="email" name="email" placeholder="you@agency.ru" autocomplete="email" inputmode="email" autofocus required />
          </div>
          ${authStep === 'code' ? `
            <div class="authField">
              <label for="login-code">Код из письма</label>
              <input id="login-code" type="text" name="code" inputmode="numeric" maxlength="6" placeholder="000000" autocomplete="one-time-code" required />
            </div>
          ` : ''}
          <button class="primaryButton" type="submit">${authStep === 'code' ? 'Подтвердить код' : 'Получить код'}</button>
        </form>
        ${authStatus ? `<div class="authStatus">${authStatus}</div>` : ''}
        ${devCode ? `<div class="authStatus dev">Dev code: <strong>${devCode}</strong></div>` : ''}
        <a class="secondaryButton" href="index.html">← На главную</a>
      </div>
    </section>
  `;
}

async function requestEmailCode(email) {
  const response = await fetch(`${API_BASE}/auth/email/request-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Не удалось отправить код');
  return payload;
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
      body: JSON.stringify({ model: aiModel, prompt: aiPrompt }),
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

async function loadIntegrationStatus() {
  try {
    const response = await fetch(`${API_BASE}/auth/yandex/status`);
    integrationStatus = response.ok ? await response.json() : {};
    if (activeView === 'integrations') render();
  } catch (error) {
    integrationStatus = { message: 'Не удалось получить статус интеграций' };
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
        <nav class="sideNav" aria-label="Навигация демо-кабинета">
          ${navItems.map((item) => `
            <button class="sideNavItem ${activeView === item.id ? 'active' : ''}" data-view="${item.id}">
              <span>${item.icon}</span>${item.label}
            </button>
          `).join('')}
        </nav>
        <div class="sidebarNote">
          <strong>Режим демо</strong>
          <p>Демо-проект один. Интеграции подключаются к рабочему backend на Vercel.</p>
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
              ${clients.map((item) => `<option value="${item.id}" ${item.id === selectedClientId ? 'selected' : ''}>${item.name}</option>`).join('')}
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
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">📊 Agency overview</span>
      <h2>Центр управления рекламой и AI-рекомендациями</h2>
      <p>Сводка по выбранному клиенту, проблемам, бюджету и действиям, которые ИИ предлагает выполнить сегодня.</p>
    </div>
    <div class="metricGrid">${agencyMetrics.map(metricCard).join('')}</div>
    <div class="dashboardLayout">
      <section class="panel scorePanel">
        <div class="scoreRing" style="--score: ${client.score}%"><strong>${client.score}</strong><span>/100</span></div>
        <div>
          <span class="muted">AI score аккаунта</span>
          <h3>${client.status}</h3>
          <p>ИИ оценил связку кампаний, целей, расходов и конверсий. Главный риск — расход без целей в РСЯ.</p>
        </div>
      </section>
      <section class="panel">
        <div class="panelHeader"><h3>Что сделать сегодня</h3><button data-view="recommendations">Все рекомендации</button></div>
        <div class="taskList">
          ${recommendations.slice(0, 3).map((item) => `<article><strong>${item.title}</strong><span>${item.impact}</span><p>${item.mode}</p></article>`).join('')}
        </div>
      </section>
    </div>
    <section class="panel">
      <div class="panelHeader"><h3>Кампании клиента</h3><button data-view="audit">Открыть аудит</button></div>
      <div class="tableWrap">
        <table>
          <thead><tr><th>Кампания</th><th>Расход</th><th>Лиды</th><th>CPA</th><th>Статус</th></tr></thead>
          <tbody>${campaigns.map((campaign) => `<tr><td>${campaign.name}</td><td>${campaign.spend}</td><td>${campaign.leads}</td><td>${campaign.cpa}</td><td><span class="tableStatus">${campaign.status}</span></td></tr>`).join('')}</tbody>
        </table>
      </div>
    </section>
  `);
}

function renderClients() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">👥 Клиенты</span><h2>Клиенты как отдельные сущности</h2><p>У каждого клиента будет своё подключение Директа, Метрики, настройки, KPI, статистика и политики автопилота.</p></div>
    <div class="clientGrid">
      ${clients.map((client) => `
        <button class="clientCard ${client.id === selectedClientId ? 'selected' : ''}" data-client-id="${client.id}">
          <span>${client.segment}</span>
          <strong>${client.name}</strong>
          <div class="clientStats"><small>Расход ${client.spend}</small><small>CPA ${client.cpa}</small><small>Score ${client.score}/100</small></div>
          <em>${client.trend}</em>
        </button>
      `).join('')}
    </div>
  `);
}

function renderAudit() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">⚡ AI-аудит</span><h2>Проблемы, которые влияют на эффективность</h2><p>Каждый пункт содержит доказательство, объект в Директе и рекомендуемое действие.</p></div>
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
  `);
}

function renderRecommendations() {
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">✨ Рекомендации</span><h2>Действия с объяснениями и контролем риска</h2><p>В production каждая карточка будет иметь dry-run, diff, approval и rollback-данные.</p></div>
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
  return renderShell(`
    <div class="pageIntro"><span class="eyebrow">🔌 Интеграции</span><h2>Подключите рабочие источники данных</h2><p>Яндекс.Директ и Метрика подключаются через OAuth. Один доступ содержит scopes direct:api, metrika:read и login:info.</p></div>
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

function renderAiAssistant() {
  const client = currentClient();
  const models = aiStatus.models?.length ? aiStatus.models : [{ id: aiModel, name: aiModel, description: 'Модель будет загружена из backend.' }];
  return renderShell(`
    <div class="pageIntro">
      <span class="eyebrow">🧠 OpenRouter</span>
      <h2>AI-слой с выбором модели</h2>
      <p>Ключ OpenRouter хранится только на backend. Интерфейс отправляет задачу в наш API, выбирает модель и показывает ответ как черновик для специалиста.</p>
    </div>
    <div class="aiGrid">
      <section class="panel aiConsole">
        <div class="panelHeader">
          <h3>Запрос к AI</h3>
          <span class="aiStatusBadge ${aiStatus.configured ? 'ready' : 'pending'}">${aiStatus.configured ? 'OpenRouter готов' : 'Нужен API key'}</span>
        </div>
        <form class="aiForm" data-ai-form>
          <label>
            <span>Модель</span>
            <select name="model" data-ai-model>
              ${models.map((model) => `<option value="${model.id}" ${model.id === aiModel ? 'selected' : ''}>${model.name}</option>`).join('')}
            </select>
          </label>
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
}

app.addEventListener('click', async (event) => {
  const viewButton = event.target.closest('[data-view]');
  const clientButton = event.target.closest('[data-client-id]');
  const integrationButton = event.target.closest('[data-integration]');

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
    activeView = 'dashboard';
    render();
  }
});

app.addEventListener('submit', async (event) => {
  const aiForm = event.target.closest('[data-ai-form]');
  if (aiForm) {
    event.preventDefault();
    const formData = new FormData(aiForm);
    aiModel = String(formData.get('model') || aiModel);
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
  authStatus = 'Отправляем запрос...';
  render();
  try {
    if (authStep === 'email') {
      const result = await requestEmailCode(email);
      authStep = 'code';
      devCode = result.dev_code;
      authStatus = 'Код отправлен на почту. Проверьте входящие и спам.';
    } else {
      const result = await verifyEmailCode(email, code);
      localStorage.setItem('directpilot_session', result.session_token);
      localStorage.setItem('directpilot_email', result.email);
      window.location.href = 'app.html';
      return;
    }
  } catch (error) {
    authStatus = `${error.message}. Проверьте SMTP-настройки backend или включите EMAIL_AUTH_DEV_MODE=true только для локальной разработки.`;
  }
  render();
});

app.addEventListener('input', (event) => {
  if (event.target.matches('input[name="email"]')) {
    authEmail = event.target.value;
  }
  if (event.target.matches('[data-ai-prompt]')) {
    aiPrompt = event.target.value;
  }
});

app.addEventListener('change', (event) => {
  if (event.target.matches('[data-client-select]')) {
    selectedClientId = event.target.value;
    render();
  }
  if (event.target.matches('[data-ai-model]')) {
    aiModel = event.target.value;
  }
});

render();

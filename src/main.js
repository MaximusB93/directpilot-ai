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
const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'clients', label: 'Клиенты', icon: '👥' },
  { id: 'audit', label: 'AI-аудит', icon: '⚡' },
  { id: 'recommendations', label: 'Рекомендации', icon: '✨' },
  { id: 'reports', label: 'Отчёты', icon: '📄' },
  { id: 'autopilot', label: 'Автопилот', icon: '🛡️' },
];

let activeView = 'landing';
let selectedClientId = clients[0].id;

function currentClient() {
  return clients.find((client) => client.id === selectedClientId) ?? clients[0];
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
      <button class="navCta" data-view="dashboard">Открыть демо-кабинет</button>
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
          <button class="primaryButton" data-view="dashboard">Открыть демо-кабинет <span>→</span></button>
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

function renderShell(content) {
  const client = currentClient();
  return `
    <div class="appShell">
      <aside class="sidebar">
        <button class="brand appBrand" data-view="landing">
          <span class="brandIcon">✦</span>
          <span>DirectPilot AI</span>
        </button>
        <nav class="sideNav" aria-label="Навигация демо-кабинета">
          ${navItems.map((item) => `
            <button class="sideNavItem ${activeView === item.id ? 'active' : ''}" data-view="${item.id}">
              <span>${item.icon}</span>${item.label}
            </button>
          `).join('')}
        </nav>
        <div class="sidebarNote">
          <strong>Режим демо</strong>
          <p>Данные моковые, структура готова для подключения Direct API, Метрики и CRM.</p>
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
      <p>Сводка по клиентам, проблемам, бюджету и действиям, которые ИИ предлагает выполнить сегодня.</p>
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
    <div class="pageIntro"><span class="eyebrow">👥 Клиенты</span><h2>Портфель агентства</h2><p>Быстрый выбор клиента, KPI и состояние рекламных аккаунтов.</p></div>
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
    dashboard: renderDashboard,
    clients: renderClients,
    audit: renderAudit,
    recommendations: renderRecommendations,
    reports: renderReports,
    autopilot: renderAutopilot,
  };
  app.innerHTML = views[activeView]();
  document.body.dataset.view = activeView;
}

app.addEventListener('click', (event) => {
  const viewButton = event.target.closest('[data-view]');
  const clientButton = event.target.closest('[data-client-id]');

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

app.addEventListener('change', (event) => {
  if (event.target.matches('[data-client-select]')) {
    selectedClientId = event.target.value;
    render();
  }
});

render();

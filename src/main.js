const kpis = [
  { label: 'Экономия бюджета', value: '18%', tone: 'green' },
  { label: 'Аномалии найдены', value: '24', tone: 'orange' },
  { label: 'CPA за 7 дней', value: '−12%', tone: 'blue' },
];

const recommendations = [
  {
    title: 'Остановить 12 ключей без конверсий',
    detail: 'Расход 48 700 ₽ за 14 дней, 0 целевых действий. Риск: низкий.',
    impact: '−9% расходов',
  },
  {
    title: 'Добавить 38 минус-фраз из поисковых запросов',
    detail: 'ИИ нашёл нерелевантные запросы в РСЯ и поиске по 5 кампаниям.',
    impact: '+6% CTR',
  },
  {
    title: 'Перераспределить бюджет в пользу бренда',
    detail: 'Кампания ограничена бюджетом, ROAS выше среднего на 42%.',
    impact: '+14 лидов',
  },
];

const features = [
  {
    icon: '⚡',
    title: 'AI-аудит аккаунта',
    text: 'Проверка структуры, целей Метрики, UTM, ключей, ставок, объявлений и расходов без конверсий.',
  },
  {
    icon: '🔔',
    title: 'Мониторинг аномалий',
    text: 'Сервис предупреждает о резком росте CPA, падении конверсий, перерасходе и проблемах модерации.',
  },
  {
    icon: '✨',
    title: 'Рекомендации с объяснениями',
    text: 'Каждое действие сопровождается причиной, прогнозом эффекта, уровнем риска и списком затронутых объектов.',
  },
  {
    icon: '🛡️',
    title: 'Безопасный автопилот',
    text: 'Dry-run, согласования, лимиты, журнал изменений и откат — ИИ действует только в рамках политик клиента.',
  },
  {
    icon: '💬',
    title: 'Чат по рекламному аккаунту',
    text: 'Можно спросить: «где сливается бюджет?», «почему вырос CPA?» или «что сделать на этой неделе?».',
  },
  {
    icon: '📄',
    title: 'Отчёты для клиентов',
    text: 'Автоматические weekly-отчёты: что изменилось, что сделал специалист и какие гипотезы проверяются.',
  },
];

const workflow = [
  'Подключите Яндекс.Директ, Метрику и CRM',
  'Получите аудит и список потерь бюджета',
  'Согласуйте безопасные рекомендации',
  'Включите автопилот для низкорисковых действий',
];

const app = document.querySelector('#app');

app.innerHTML = `
  <nav class="nav">
    <a class="brand" href="#top" aria-label="DirectPilot AI">
      <span class="brandIcon">✦</span>
      DirectPilot AI
    </a>
    <div class="navLinks" aria-label="Главная навигация">
      <a href="#features">Возможности</a>
      <a href="#workflow">Как работает</a>
      <a href="#security">Безопасность</a>
    </div>
    <a class="navCta" href="mailto:hello@directpilot.ai">Запросить демо</a>
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
        <a class="primaryButton" href="#demo">Посмотреть прототип <span>→</span></a>
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
          <strong>Интернет-магазин мебели</strong>
        </div>
        <span class="status"><span></span> AI анализ завершён</span>
      </div>

      <div class="kpiGrid">
        ${kpis.map((kpi) => `
          <article class="kpi ${kpi.tone}">
            <span>${kpi.label}</span>
            <strong>${kpi.value}</strong>
          </article>
        `).join('')}
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
        ${recommendations.map((item) => `
          <article class="recommendation">
            <div>
              <strong>${item.title}</strong>
              <p>${item.detail}</p>
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
      ${features.map((feature) => `
        <article class="featureCard">
          <span class="featureIcon">${feature.icon}</span>
          <h3>${feature.title}</h3>
          <p>${feature.text}</p>
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
      ${workflow.map((step, index) => `
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

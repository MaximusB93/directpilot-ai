const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
const WORDSTAT_VIEW_ID = 'wordstat';
const WORDSTAT_DEFAULT_PHRASES = 'купить диван\nдиван кровать\nугловой диван';

const wordstatState = {
  mounted: false,
  active: false,
  loading: false,
  status: '',
  error: '',
  connection: null,
  result: null,
  form: defaultWordstatForm(),
};

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

function getSessionToken() {
  return window.localStorage.getItem('directpilot_session') || '';
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${resolveApiBase()}${path}`, { ...options, headers });
  if (response.status === 401) {
    localStorage.removeItem('directpilot_session');
    localStorage.removeItem('directpilot_email');
    window.location.href = 'login.html';
    throw new Error('Authentication required');
  }
  return response;
}

function defaultWordstatForm() {
  const now = new Date();
  const from = new Date(now.getFullYear() - 1, 0, 1);
  return {
    phrases: WORDSTAT_DEFAULT_PHRASES,
    period: 'MONTHLY',
    fromDate: toInputDate(from),
    toDate: toInputDate(now),
    regions: '225',
    devices: 'DEVICE_ALL',
    forceRefresh: false,
  };
}

function toInputDate(date) {
  return date.toISOString().slice(0, 10);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? new Intl.NumberFormat('ru-RU').format(number) : '0';
}

function formatPercent(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? `${number > 0 ? '+' : ''}${number.toFixed(2)}%` : '—';
}

function parseList(value) {
  return String(value || '')
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parsePhrases(value) {
  return String(value || '')
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function selectedClientIdFromStorageOrDom() {
  const select = document.querySelector('[data-client-select]');
  if (select?.value) return select.value;
  const email = (window.localStorage.getItem('directpilot_email') || '').trim().toLowerCase();
  const key = email ? `directpilot_selected_client_id_${email}` : 'directpilot_selected_client_id';
  return window.localStorage.getItem(key) || '';
}

function ensureWordstatNav() {
  const nav = document.querySelector('.sideNav');
  if (!nav || nav.querySelector('[data-wordstat-view]')) return;
  const button = document.createElement('button');
  button.className = 'sideNavItem';
  button.type = 'button';
  button.dataset.wordstatView = WORDSTAT_VIEW_ID;
  button.innerHTML = '<span>📈</span>Спрос / Wordstat';
  nav.appendChild(button);
}

function setWordstatNavActive(active) {
  document.querySelectorAll('.sideNavItem').forEach((item) => item.classList.remove('active'));
  const button = document.querySelector('[data-wordstat-view]');
  if (button) button.classList.toggle('active', Boolean(active));
}

async function loadWordstatConnection() {
  try {
    const response = await apiFetch('/wordstat/connection');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось проверить Wordstat');
    wordstatState.connection = payload;
  } catch (error) {
    if (error.message === 'Authentication required') return;
    wordstatState.connection = {
      configured: false,
      can_call_api: false,
      provider: 'yandex_search_api',
      message: error.message,
    };
  }
}

function renderWordstatPage() {
  const workspace = document.querySelector('.workspace');
  if (!workspace) return;
  wordstatState.active = true;
  setWordstatNavActive(true);

  const result = wordstatState.result;
  const connection = wordstatState.connection;
  const connectionReady = Boolean(connection?.configured);
  const totalPoints = result?.series?.reduce((sum, item) => sum + (item.points?.length || 0), 0) || 0;
  const completed = result?.meta?.completedPhrases ?? 0;
  const failed = result?.meta?.failedPhrases ?? 0;

  workspace.innerHTML = `
    <header class="appHeader">
      <div>
        <span class="muted">Модуль спроса</span>
        <h1>Спрос / Wordstat</h1>
      </div>
      <div class="clientSelect">
        <span>Источник</span>
        <strong>${connectionReady ? 'Wordstat готов' : 'Нужно подключение'}</strong>
        <small>${escapeHtml(connection?.provider || 'yandex_search_api')}</small>
      </div>
    </header>

    <section class="panel clientSourcePanel">
      <div><span class="muted">API</span><strong>${connectionReady ? 'Подключён' : 'Не готов'}</strong><small>${escapeHtml(connection?.message || 'Статус ещё не загружен')}</small></div>
      <div><span class="muted">Период</span><strong>${escapeHtml(wordstatState.form.period)}</strong><small>${escapeHtml(wordstatState.form.fromDate)} → ${escapeHtml(wordstatState.form.toDate)}</small></div>
      <div><span class="muted">Фразы</span><strong>${formatNumber(parsePhrases(wordstatState.form.phrases).length)}</strong><small>batch-запрос</small></div>
      <div><span class="muted">Точки</span><strong>${formatNumber(totalPoints)}</strong><small>из БД или API</small></div>
      <div><span class="muted">Успешно</span><strong>${formatNumber(completed)}</strong><small>ошибок: ${formatNumber(failed)}</small></div>
    </section>

    <div class="pageIntro">
      <span class="eyebrow">📈 Wordstat Dynamics</span>
      <h2>Динамика частотности по нескольким фразам</h2>
      <p>Введите список ключевых фраз, выберите период и регион. Backend сам обойдёт Wordstat по одной фразе, сохранит результат в БД и вернёт сравнение MoM, YoY и индекс от первого периода.</p>
    </div>

    <section class="panel">
      <form class="clientConnectForm" data-wordstat-form>
        <label class="authField" style="grid-column:1 / -1;">
          <span>Ключевые фразы, по одной на строку</span>
          <textarea name="phrases" rows="6" placeholder="купить диван&#10;диван кровать&#10;угловой диван">${escapeHtml(wordstatState.form.phrases)}</textarea>
        </label>
        <label class="authField">
          <span>Группировка</span>
          <select name="period">
            <option value="MONTHLY" ${wordstatState.form.period === 'MONTHLY' ? 'selected' : ''}>По месяцам</option>
            <option value="WEEKLY" ${wordstatState.form.period === 'WEEKLY' ? 'selected' : ''}>По неделям</option>
            <option value="DAILY" ${wordstatState.form.period === 'DAILY' ? 'selected' : ''}>По дням</option>
          </select>
        </label>
        <label class="authField">
          <span>Дата с</span>
          <input type="date" name="fromDate" value="${escapeHtml(wordstatState.form.fromDate)}" />
        </label>
        <label class="authField">
          <span>Дата по</span>
          <input type="date" name="toDate" value="${escapeHtml(wordstatState.form.toDate)}" />
        </label>
        <label class="authField">
          <span>Регионы</span>
          <input name="regions" value="${escapeHtml(wordstatState.form.regions)}" placeholder="225 или 213, 2" />
          <small>225 — Россия, 213 — Москва. Пусто = без фильтра.</small>
        </label>
        <label class="authField">
          <span>Устройства</span>
          <select name="devices">
            <option value="DEVICE_ALL" ${wordstatState.form.devices === 'DEVICE_ALL' ? 'selected' : ''}>Все</option>
            <option value="DEVICE_DESKTOP" ${wordstatState.form.devices === 'DEVICE_DESKTOP' ? 'selected' : ''}>Desktop</option>
            <option value="DEVICE_PHONE" ${wordstatState.form.devices === 'DEVICE_PHONE' ? 'selected' : ''}>Phone</option>
            <option value="DEVICE_TABLET" ${wordstatState.form.devices === 'DEVICE_TABLET' ? 'selected' : ''}>Tablet</option>
          </select>
        </label>
        <label class="authField">
          <span>Кэш</span>
          <select name="forceRefresh">
            <option value="false" ${!wordstatState.form.forceRefresh ? 'selected' : ''}>Использовать кэш</option>
            <option value="true" ${wordstatState.form.forceRefresh ? 'selected' : ''}>Принудительно обновить</option>
          </select>
        </label>
        <div class="heroActions" style="grid-column:1 / -1;">
          <button class="approveButton" type="submit" ${wordstatState.loading ? 'disabled' : ''}>${wordstatState.loading ? 'Загружаем...' : 'Получить динамику'}</button>
          <button class="secondaryButton" type="button" data-wordstat-demo>Демо-фразы</button>
          ${result ? '<button class="secondaryButton" type="button" data-wordstat-copy-json>Скопировать JSON</button>' : ''}
        </div>
      </form>
      ${wordstatState.status ? `<div class="authStatus integrationStatus">${escapeHtml(wordstatState.status)}</div>` : ''}
      ${wordstatState.error ? `<div class="authStatus aiError">${escapeHtml(wordstatState.error)}</div>` : ''}
    </section>

    ${result ? renderWordstatResult(result) : renderWordstatEmptyState()}
  `;
}

function renderWordstatEmptyState() {
  return `
    <section class="panel emptyStatePanel compact">
      <h3>Данных пока нет</h3>
      <p>Запустите batch-запрос. Если всё подключено, здесь появятся таблица по фразам, MoM/YoY и индексный ряд. Красота, почти как Excel, только без желания закрыть ноутбук.</p>
    </section>
  `;
}

function renderWordstatResult(result) {
  const summary = result.summary || {};
  return `
    <section class="panel">
      <div class="panelHeader">
        <div>
          <h3>Итоги batch-запроса</h3>
          <p>Статус: ${escapeHtml(result.status)} · batch: ${escapeHtml(result.batchId || '—')}</p>
        </div>
        <span class="aiStatusBadge ${result.status === 'completed' ? 'ready' : 'pending'}">${escapeHtml(result.meta?.period || 'Wordstat')}</span>
      </div>
      <div class="kpiGrid">
        <article class="kpi green"><span>Лидер по росту</span><strong>${escapeHtml(summary.topGrowthPhrase || '—')}</strong></article>
        <article class="kpi orange"><span>Просадка</span><strong>${escapeHtml(summary.topDeclinePhrase || '—')}</strong></article>
        <article class="kpi blue"><span>Макс. спрос</span><strong>${escapeHtml(summary.maxCountPhrase || '—')}</strong></article>
      </div>
    </section>
    <section class="panel">
      <h3>Сравнение фраз</h3>
      <div class="tableWrap">
        <table>
          <thead><tr><th>Фраза</th><th>Источник</th><th>Точек</th><th>Сумма</th><th>Первый</th><th>Последний</th><th>Рост</th></tr></thead>
          <tbody>
            ${(summary.phrases || []).map((item) => `
              <tr>
                <td>${escapeHtml(item.phrase)}</td>
                <td>${escapeHtml((result.series || []).find((series) => series.phrase === item.phrase)?.source || '—')}</td>
                <td>${formatNumber((result.series || []).find((series) => series.phrase === item.phrase)?.points?.length || 0)}</td>
                <td>${formatNumber(item.total)}</td>
                <td>${formatNumber(item.firstCount)}</td>
                <td>${formatNumber(item.lastCount)}</td>
                <td>${formatPercent(item.growthPercent)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h3>Детализация по периодам</h3>
      ${(result.series || []).map(renderWordstatSeries).join('')}
    </section>
  `;
}

function renderWordstatSeries(series) {
  if (series.error) {
    return `<div class="authStatus aiError"><strong>${escapeHtml(series.phrase)}</strong>: ${escapeHtml(series.error)}</div>`;
  }
  const points = series.points || [];
  return `
    <details class="aiToolTrace" open>
      <summary>${escapeHtml(series.phrase)} · ${formatNumber(points.length)} точек · ${escapeHtml(series.source || '—')}</summary>
      <div class="tableWrap">
        <table>
          <thead><tr><th>Дата</th><th>Частотность</th><th>Share</th><th>MoM</th><th>YoY</th><th>Index</th></tr></thead>
          <tbody>
            ${points.map((point) => `
              <tr>
                <td>${escapeHtml(point.date)}</td>
                <td>${formatNumber(point.count)}</td>
                <td>${point.share == null ? '—' : Number(point.share).toPrecision(4)}</td>
                <td>${formatPercent(point.mom)}</td>
                <td>${formatPercent(point.yoy)}</td>
                <td>${point.index == null ? '—' : formatNumber(point.index)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </details>
  `;
}

async function openWordstatView() {
  wordstatState.active = true;
  wordstatState.status = 'Проверяем подключение Wordstat...';
  wordstatState.error = '';
  ensureWordstatNav();
  renderWordstatPage();
  await loadWordstatConnection();
  wordstatState.status = wordstatState.connection?.configured
    ? 'Wordstat API готов. Можно загружать динамику.'
    : 'Wordstat API не готов: проверьте YANDEX_SEARCH_API_KEY / YANDEX_SEARCH_FOLDER_ID или OAuth.';
  renderWordstatPage();
}

async function submitWordstatForm(form) {
  const formData = new FormData(form);
  wordstatState.form = {
    phrases: String(formData.get('phrases') || '').trim(),
    period: String(formData.get('period') || 'MONTHLY'),
    fromDate: String(formData.get('fromDate') || ''),
    toDate: String(formData.get('toDate') || ''),
    regions: String(formData.get('regions') || '').trim(),
    devices: String(formData.get('devices') || 'DEVICE_ALL'),
    forceRefresh: String(formData.get('forceRefresh') || 'false') === 'true',
  };

  const phrases = parsePhrases(wordstatState.form.phrases);
  if (!phrases.length) {
    wordstatState.error = 'Добавьте хотя бы одну фразу.';
    renderWordstatPage();
    return;
  }
  if (!wordstatState.form.fromDate || !wordstatState.form.toDate) {
    wordstatState.error = 'Укажите даты периода.';
    renderWordstatPage();
    return;
  }

  wordstatState.loading = true;
  wordstatState.status = `Отправляем batch-запрос: ${phrases.length} фраз.`;
  wordstatState.error = '';
  renderWordstatPage();

  try {
    const response = await apiFetch('/wordstat/dynamics/batch', {
      method: 'POST',
      body: JSON.stringify({
        phrases,
        period: wordstatState.form.period,
        fromDate: wordstatState.form.fromDate,
        toDate: wordstatState.form.toDate,
        regions: parseList(wordstatState.form.regions),
        devices: [wordstatState.form.devices],
        clientId: selectedClientIdFromStorageOrDom() || null,
        forceRefresh: wordstatState.form.forceRefresh,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Wordstat API не вернул данные');
    wordstatState.result = payload;
    wordstatState.status = `Готово: ${payload.meta?.completedPhrases || 0} фраз, ошибок: ${payload.meta?.failedPhrases || 0}.`;
  } catch (error) {
    if (error.message === 'Authentication required') return;
    wordstatState.error = error.message;
  } finally {
    wordstatState.loading = false;
    renderWordstatPage();
  }
}

async function copyWordstatJson() {
  await navigator.clipboard?.writeText(JSON.stringify(wordstatState.result || {}, null, 2));
  wordstatState.status = 'JSON результата скопирован.';
  renderWordstatPage();
}

function mountWordstatExtension() {
  if (wordstatState.mounted) return;
  wordstatState.mounted = true;
  ensureWordstatNav();

  const observer = new MutationObserver(() => {
    ensureWordstatNav();
    if (wordstatState.active && !document.querySelector('[data-wordstat-form]')) {
      renderWordstatPage();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  document.addEventListener('click', async (event) => {
    const navButton = event.target.closest('[data-wordstat-view]');
    if (navButton) {
      event.preventDefault();
      await openWordstatView();
      return;
    }
    if (event.target.closest('[data-wordstat-demo]')) {
      wordstatState.form.phrases = WORDSTAT_DEFAULT_PHRASES;
      wordstatState.status = 'Демо-фразы вставлены.';
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-copy-json]')) {
      await copyWordstatJson();
    }
  });

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-view], [data-go-view]') && !event.target.closest('[data-wordstat-view]')) {
      wordstatState.active = false;
      setWordstatNavActive(false);
    }
  }, true);

  document.addEventListener('submit', async (event) => {
    const form = event.target.closest('[data-wordstat-form]');
    if (!form) return;
    event.preventDefault();
    await submitWordstatForm(form);
  });
}

if (document.body.dataset.page === 'app') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountWordstatExtension);
  } else {
    mountWordstatExtension();
  }
}

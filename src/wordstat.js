const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
const WORDSTAT_VIEW_ID = 'wordstat';
const WORDSTAT_DEFAULT_PHRASES = 'купить диван\nдиван кровать\nугловой диван';
const WORDSTAT_COLORS = ['#2563eb', '#16a34a', '#f97316', '#9333ea', '#dc2626', '#0891b2', '#4f46e5', '#65a30d'];
const WORDSTAT_REGION_GROUPS = [
  {
    title: 'Основные',
    regions: [
      { id: '225', name: 'Россия' },
      { id: '213', name: 'Москва' },
      { id: '1', name: 'Москва и область' },
      { id: '2', name: 'Санкт-Петербург' },
      { id: '10174', name: 'Санкт-Петербург и Ленинградская область' },
    ],
  },
  {
    title: 'Крупные города',
    regions: [
      { id: '43', name: 'Казань' },
      { id: '54', name: 'Екатеринбург' },
      { id: '65', name: 'Новосибирск' },
      { id: '39', name: 'Ростов-на-Дону' },
      { id: '35', name: 'Краснодар' },
      { id: '172', name: 'Уфа' },
      { id: '51', name: 'Самара' },
      { id: '55', name: 'Пермь' },
      { id: '193', name: 'Воронеж' },
      { id: '47', name: 'Нижний Новгород' },
    ],
  },
  {
    title: 'Регионы / курорты',
    regions: [
      { id: '1095', name: 'Краснодарский край' },
      { id: '239', name: 'Сочи' },
      { id: '1107', name: 'Ростовская область' },
      { id: '11119', name: 'Казань и Татарстан' },
      { id: '11162', name: 'Свердловская область' },
    ],
  },
];
const WORDSTAT_REGION_BY_ID = new Map(WORDSTAT_REGION_GROUPS.flatMap((group) => group.regions.map((region) => [region.id, region])));

const wordstatState = {
  mounted: false,
  active: false,
  loading: false,
  compareLoading: false,
  status: '',
  error: '',
  connection: null,
  result: null,
  comparison: null,
  comparisonRange: null,
  form: defaultWordstatForm(),
};

function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');
  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') return 'http://localhost:8000/api/v1';
  if (hostname === 'maximusb93.github.io') return DEFAULT_PRODUCTION_API_BASE;
  return `${origin}/api/v1`;
}

function getSessionToken() {
  return window.localStorage.getItem('directpilot_session') || '';
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
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
  const today = startOfDay(new Date());
  const from = addMonths(today, -3);
  return {
    phrases: WORDSTAT_DEFAULT_PHRASES,
    period: 'WEEKLY',
    fromDate: toInputDate(from),
    toDate: toInputDate(today),
    regions: ['225'],
    devices: 'DEVICE_ALL',
    forceRefresh: false,
  };
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function addMonths(date, months) {
  const result = new Date(date);
  const day = result.getDate();
  result.setMonth(result.getMonth() + months, 1);
  const maxDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
  result.setDate(Math.min(day, maxDay));
  return result;
}

function addDays(date, days) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function parseInputDate(value) {
  const [year, month, day] = String(value || '').split('-').map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function toInputDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
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

function parsePhrases(value) {
  return String(value || '').split(/\n+/).map((item) => item.trim()).filter(Boolean);
}

function selectedClientIdFromStorageOrDom() {
  const select = document.querySelector('[data-client-select]');
  if (select?.value) return select.value;
  const email = (window.localStorage.getItem('directpilot_email') || '').trim().toLowerCase();
  const key = email ? `directpilot_selected_client_id_${email}` : 'directpilot_selected_client_id';
  return window.localStorage.getItem(key) || '';
}

function selectedRegionIdsFromForm(form) {
  const checked = [...form.querySelectorAll('[data-wordstat-region]:checked')].map((item) => item.value);
  const custom = String(form.querySelector('[name="customRegions"]')?.value || '')
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return [...new Set([...checked, ...custom])];
}

function regionLabel(id) {
  const region = WORDSTAT_REGION_BY_ID.get(String(id));
  return region ? `${region.name} (${region.id})` : String(id);
}

function regionsSummary(ids) {
  if (!ids?.length) return 'Все регионы';
  return ids.map(regionLabel).join(', ');
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
    wordstatState.connection = { configured: false, can_call_api: false, provider: 'yandex_search_api', message: error.message };
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
      <div><span class="muted">Модуль спроса</span><h1>Спрос / Wordstat</h1></div>
      <div class="clientSelect"><span>Источник</span><strong>${connectionReady ? 'Wordstat готов' : 'Нужно подключение'}</strong><small>${escapeHtml(connection?.provider || 'yandex_search_api')}</small></div>
    </header>

    <section class="panel clientSourcePanel">
      <div><span class="muted">API</span><strong>${connectionReady ? 'Подключён' : 'Не готов'}</strong><small>${escapeHtml(connection?.message || 'Статус ещё не загружен')}</small></div>
      <div><span class="muted">Период</span><strong>${escapeHtml(wordstatState.form.period)}</strong><small>${escapeHtml(wordstatState.form.fromDate)} → ${escapeHtml(wordstatState.form.toDate)}</small></div>
      <div><span class="muted">Регионы</span><strong>${formatNumber(wordstatState.form.regions.length || 0)}</strong><small>${escapeHtml(regionsSummary(wordstatState.form.regions))}</small></div>
      <div><span class="muted">Фразы</span><strong>${formatNumber(parsePhrases(wordstatState.form.phrases).length)}</strong><small>batch-запрос</small></div>
      <div><span class="muted">Точки</span><strong>${formatNumber(totalPoints)}</strong><small>из БД или API</small></div>
      <div><span class="muted">Успешно</span><strong>${formatNumber(completed)}</strong><small>ошибок: ${formatNumber(failed)}</small></div>
    </section>

    <div class="pageIntro">
      <span class="eyebrow">📈 Wordstat Dynamics</span>
      <h2>Динамика частотности по нескольким фразам</h2>
      <p>По умолчанию берём последние 3 месяца до сегодняшней даты. Можно выбрать несколько регионов чекбоксами, построить график и сравнить текущий период с предыдущим.</p>
    </div>

    <section class="panel">
      <form class="clientConnectForm" data-wordstat-form>
        <label class="authField" style="grid-column:1 / -1;"><span>Ключевые фразы, по одной на строку</span><textarea name="phrases" rows="6" placeholder="купить диван&#10;диван кровать&#10;угловой диван">${escapeHtml(wordstatState.form.phrases)}</textarea></label>
        <label class="authField"><span>Группировка</span><select name="period"><option value="MONTHLY" ${wordstatState.form.period === 'MONTHLY' ? 'selected' : ''}>По месяцам</option><option value="WEEKLY" ${wordstatState.form.period === 'WEEKLY' ? 'selected' : ''}>По неделям</option><option value="DAILY" ${wordstatState.form.period === 'DAILY' ? 'selected' : ''}>По дням</option></select></label>
        <label class="authField"><span>Дата с</span><input type="date" name="fromDate" value="${escapeHtml(wordstatState.form.fromDate)}" /></label>
        <label class="authField"><span>Дата по</span><input type="date" name="toDate" value="${escapeHtml(wordstatState.form.toDate)}" /></label>
        <label class="authField"><span>Устройства</span><select name="devices"><option value="DEVICE_ALL" ${wordstatState.form.devices === 'DEVICE_ALL' ? 'selected' : ''}>Все</option><option value="DEVICE_DESKTOP" ${wordstatState.form.devices === 'DEVICE_DESKTOP' ? 'selected' : ''}>Desktop</option><option value="DEVICE_PHONE" ${wordstatState.form.devices === 'DEVICE_PHONE' ? 'selected' : ''}>Phone</option><option value="DEVICE_TABLET" ${wordstatState.form.devices === 'DEVICE_TABLET' ? 'selected' : ''}>Tablet</option></select></label>
        <label class="authField"><span>Кэш</span><select name="forceRefresh"><option value="false" ${!wordstatState.form.forceRefresh ? 'selected' : ''}>Использовать кэш</option><option value="true" ${wordstatState.form.forceRefresh ? 'selected' : ''}>Принудительно обновить</option></select></label>
        <div class="authField" style="grid-column:1 / -1;">
          <span>Регионы</span>
          <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:14px; margin-top:8px;">
            ${WORDSTAT_REGION_GROUPS.map(renderRegionGroup).join('')}
          </div>
          <label style="display:block; margin-top:12px;"><span class="muted">Другие коды регионов через запятую</span><input name="customRegions" value="${escapeHtml(customRegionsOnly(wordstatState.form.regions).join(', '))}" placeholder="Например: 977, 11029" /></label>
        </div>
        <div class="heroActions" style="grid-column:1 / -1;">
          <button class="approveButton" type="submit" ${wordstatState.loading ? 'disabled' : ''}>${wordstatState.loading ? 'Загружаем...' : 'Получить динамику'}</button>
          <button class="secondaryButton" type="button" data-wordstat-compare ${!result || wordstatState.compareLoading ? 'disabled' : ''}>${wordstatState.compareLoading ? 'Сравниваем...' : 'Сравнить с предыдущим периодом'}</button>
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

function renderRegionGroup(group) {
  return `
    <fieldset style="border:1px solid var(--border, #d8e0ec); border-radius:16px; padding:12px;">
      <legend>${escapeHtml(group.title)}</legend>
      ${group.regions.map((region) => `
        <label style="display:flex; align-items:center; gap:8px; margin:6px 0; cursor:pointer;">
          <input type="checkbox" data-wordstat-region value="${escapeHtml(region.id)}" ${wordstatState.form.regions.includes(region.id) ? 'checked' : ''} />
          <span>${escapeHtml(region.name)} <small class="muted">${escapeHtml(region.id)}</small></span>
        </label>
      `).join('')}
    </fieldset>
  `;
}

function customRegionsOnly(ids) {
  return (ids || []).filter((id) => !WORDSTAT_REGION_BY_ID.has(String(id)));
}

function renderWordstatEmptyState() {
  return `<section class="panel emptyStatePanel compact"><h3>Данных пока нет</h3><p>Запустите batch-запрос. График, сравнение периодов и суммарная частотность появятся здесь. Почти BI, только без десяти созвонов о том, почему цифры не сходятся.</p></section>`;
}

function renderWordstatResult(result) {
  const summary = result.summary || {};
  return `
    <section class="panel">
      <div class="panelHeader"><div><h3>Итоги batch-запроса</h3><p>Статус: ${escapeHtml(result.status)} · batch: ${escapeHtml(result.batchId || '—')}</p></div><span class="aiStatusBadge ${result.status === 'completed' ? 'ready' : 'pending'}">${escapeHtml(result.meta?.period || 'Wordstat')}</span></div>
      <div class="kpiGrid"><article class="kpi green"><span>Лидер по росту</span><strong>${escapeHtml(summary.topGrowthPhrase || '—')}</strong></article><article class="kpi orange"><span>Просадка</span><strong>${escapeHtml(summary.topDeclinePhrase || '—')}</strong></article><article class="kpi blue"><span>Макс. спрос</span><strong>${escapeHtml(summary.maxCountPhrase || '—')}</strong></article></div>
    </section>
    ${renderWordstatChart(result, wordstatState.comparison)}
    ${wordstatState.comparison ? renderComparisonPanel(result, wordstatState.comparison) : ''}
    <section class="panel"><h3>Сравнение фраз</h3>${renderPhraseSummaryTable(result)}</section>
    <section class="panel"><h3>Детализация по периодам</h3>${renderTotalSeries(result)}${(result.series || []).map(renderWordstatSeries).join('')}</section>
  `;
}

function renderPhraseSummaryTable(result) {
  const summaryRows = result.summary?.phrases || [];
  const total = buildTotalSummary(result);
  return `
    <div class="tableWrap"><table><thead><tr><th>Фраза</th><th>Источник</th><th>Точек</th><th>Сумма</th><th>Первый</th><th>Последний</th><th>Рост</th></tr></thead><tbody>
      ${summaryRows.map((item) => {
        const series = (result.series || []).find((row) => row.phrase === item.phrase);
        return `<tr><td>${escapeHtml(item.phrase)}</td><td>${escapeHtml(series?.source || '—')}</td><td>${formatNumber(series?.points?.length || 0)}</td><td>${formatNumber(item.total)}</td><td>${formatNumber(item.firstCount)}</td><td>${formatNumber(item.lastCount)}</td><td>${formatPercent(item.growthPercent)}</td></tr>`;
      }).join('')}
      <tr><td><strong>Сумма всех фраз</strong></td><td>total</td><td>${formatNumber(total.points)}</td><td><strong>${formatNumber(total.total)}</strong></td><td>${formatNumber(total.firstCount)}</td><td>${formatNumber(total.lastCount)}</td><td>${formatPercent(total.growthPercent)}</td></tr>
    </tbody></table></div>
  `;
}

function renderWordstatChart(result, comparison) {
  const series = (result.series || []).filter((item) => !item.error && item.points?.length);
  if (!series.length) return '';
  const width = 980;
  const height = 360;
  const padding = { left: 58, right: 24, top: 24, bottom: 52 };
  const allPoints = [
    ...series.flatMap((item) => item.points.map((point) => Number(point.count || 0))),
    ...(comparison?.series || []).flatMap((item) => (item.points || []).map((point) => Number(point.count || 0))),
  ];
  const maxY = Math.max(1, ...allPoints);
  const maxLen = Math.max(1, ...series.map((item) => item.points.length), ...(comparison?.series || []).map((item) => item.points?.length || 0));
  const x = (index) => padding.left + (index / Math.max(1, maxLen - 1)) * (width - padding.left - padding.right);
  const y = (count) => padding.top + (1 - Number(count || 0) / maxY) * (height - padding.top - padding.bottom);
  const polyline = (points) => points.map((point, index) => `${x(index)},${y(point.count)}`).join(' ');
  return `
    <section class="panel"><div class="panelHeader"><div><h3>График динамики</h3><p>${escapeHtml(regionsSummary(result.meta?.regions || wordstatState.form.regions))}</p></div><span class="aiStatusBadge ready">${formatNumber(series.length)} линий</span></div>
      <div style="overflow:auto;"><svg viewBox="0 0 ${width} ${height}" style="min-width:780px; width:100%; height:auto; background:#f8fafc; border-radius:18px;">
        ${[0, 0.25, 0.5, 0.75, 1].map((tick) => `<line x1="${padding.left}" y1="${y(maxY * tick)}" x2="${width - padding.right}" y2="${y(maxY * tick)}" stroke="#d8e0ec"/><text x="12" y="${y(maxY * tick) + 4}" font-size="12" fill="#64748b">${formatNumber(Math.round(maxY * tick))}</text>`).join('')}
        ${series.map((item, index) => `<polyline points="${polyline(item.points)}" fill="none" stroke="${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`).join('')}
        ${(comparison?.series || []).filter((item) => !item.error && item.points?.length).map((item, index) => `<polyline points="${polyline(item.points)}" fill="none" stroke="${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]}" stroke-width="3" stroke-dasharray="8 8" opacity="0.7" stroke-linecap="round" stroke-linejoin="round"/>`).join('')}
        <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="#94a3b8"/>
      </svg></div>
      <div style="display:flex; flex-wrap:wrap; gap:12px; margin-top:12px;">${series.map((item, index) => `<span><i style="display:inline-block;width:18px;height:4px;background:${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]};vertical-align:middle;margin-right:6px;"></i>${escapeHtml(item.phrase)}</span>`).join('')}${comparison ? '<span><i style="display:inline-block;width:18px;height:0;border-top:4px dashed #64748b;vertical-align:middle;margin-right:6px;"></i>пунктир = предыдущий период</span>' : ''}</div>
    </section>
  `;
}

function renderComparisonPanel(current, previous) {
  const currentByPhrase = new Map((current.summary?.phrases || []).map((item) => [item.phrase, item]));
  const previousByPhrase = new Map((previous.summary?.phrases || []).map((item) => [item.phrase, item]));
  const phrases = [...new Set([...currentByPhrase.keys(), ...previousByPhrase.keys()])];
  return `
    <section class="panel"><div class="panelHeader"><div><h3>Сравнение с предыдущим периодом</h3><p>${escapeHtml(wordstatState.comparisonRange?.fromDate || '—')} → ${escapeHtml(wordstatState.comparisonRange?.toDate || '—')}</p></div><span class="aiStatusBadge ready">compare</span></div>
      <div class="tableWrap"><table><thead><tr><th>Фраза</th><th>Текущий период</th><th>Предыдущий период</th><th>Разница</th><th>%</th></tr></thead><tbody>
        ${phrases.map((phrase) => {
          const currentTotal = currentByPhrase.get(phrase)?.total || 0;
          const previousTotal = previousByPhrase.get(phrase)?.total || 0;
          const diff = currentTotal - previousTotal;
          return `<tr><td>${escapeHtml(phrase)}</td><td>${formatNumber(currentTotal)}</td><td>${formatNumber(previousTotal)}</td><td>${diff > 0 ? '+' : ''}${formatNumber(diff)}</td><td>${formatPercent(percentDelta(currentTotal, previousTotal))}</td></tr>`;
        }).join('')}
        ${renderComparisonTotalRow(current, previous)}
      </tbody></table></div>
    </section>
  `;
}

function renderComparisonTotalRow(current, previous) {
  const currentTotal = buildTotalSummary(current).total;
  const previousTotal = buildTotalSummary(previous).total;
  const diff = currentTotal - previousTotal;
  return `<tr><td><strong>Сумма всех фраз</strong></td><td><strong>${formatNumber(currentTotal)}</strong></td><td><strong>${formatNumber(previousTotal)}</strong></td><td><strong>${diff > 0 ? '+' : ''}${formatNumber(diff)}</strong></td><td><strong>${formatPercent(percentDelta(currentTotal, previousTotal))}</strong></td></tr>`;
}

function renderTotalSeries(result) {
  const points = buildTotalPoints(result);
  if (!points.length) return '';
  return renderSeriesTable({ phrase: 'Сумма всех фраз', source: 'total', points });
}

function renderWordstatSeries(series) {
  if (series.error) return `<div class="authStatus aiError"><strong>${escapeHtml(series.phrase)}</strong>: ${escapeHtml(series.error)}</div>`;
  return renderSeriesTable(series);
}

function renderSeriesTable(series) {
  const points = series.points || [];
  return `
    <details class="aiToolTrace" open><summary>${escapeHtml(series.phrase)} · ${formatNumber(points.length)} точек · ${escapeHtml(series.source || '—')}</summary><div class="tableWrap"><table><thead><tr><th>Дата</th><th>Частотность</th><th>Share</th><th>MoM</th><th>YoY</th><th>Index</th></tr></thead><tbody>
      ${points.map((point) => `<tr><td>${escapeHtml(point.date)}</td><td>${formatNumber(point.count)}</td><td>${point.share == null ? '—' : Number(point.share).toPrecision(4)}</td><td>${formatPercent(point.mom)}</td><td>${formatPercent(point.yoy)}</td><td>${point.index == null ? '—' : formatNumber(point.index)}</td></tr>`).join('')}
    </tbody></table></div></details>
  `;
}

function buildTotalPoints(result) {
  const byDate = new Map();
  for (const series of result.series || []) {
    if (series.error) continue;
    for (const point of series.points || []) {
      const existing = byDate.get(point.date) || { date: point.date, count: 0, share: null };
      existing.count += Number(point.count || 0);
      byDate.set(point.date, existing);
    }
  }
  const ordered = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  const first = ordered.find((point) => point.count)?.count || 0;
  let previous = null;
  return ordered.map((point) => {
    const enriched = { ...point, mom: percentDelta(point.count, previous), yoy: null, index: first ? Math.round((point.count / first) * 10000) / 100 : null };
    previous = point.count;
    return enriched;
  });
}

function buildTotalSummary(result) {
  const points = buildTotalPoints(result);
  const total = points.reduce((sum, point) => sum + Number(point.count || 0), 0);
  const firstCount = points[0]?.count || 0;
  const lastCount = points.at(-1)?.count || 0;
  return { points: points.length, total, firstCount, lastCount, growthPercent: percentDelta(lastCount, firstCount) };
}

function percentDelta(current, previous) {
  if (previous === null || previous === undefined || Number(previous) === 0) return null;
  return Math.round(((Number(current || 0) - Number(previous)) / Number(previous)) * 10000) / 100;
}

function previousPeriodRange() {
  const from = parseInputDate(wordstatState.form.fromDate);
  const to = parseInputDate(wordstatState.form.toDate);
  if (!from || !to) return null;
  const days = Math.max(1, Math.round((to - from) / 86400000) + 1);
  const prevTo = addDays(from, -1);
  const prevFrom = addDays(prevTo, -(days - 1));
  return { fromDate: toInputDate(prevFrom), toDate: toInputDate(prevTo) };
}

function collectRequestBody({ fromDate = wordstatState.form.fromDate, toDate = wordstatState.form.toDate, forceRefresh = wordstatState.form.forceRefresh } = {}) {
  return {
    phrases: parsePhrases(wordstatState.form.phrases),
    period: wordstatState.form.period,
    fromDate,
    toDate,
    regions: wordstatState.form.regions,
    devices: [wordstatState.form.devices],
    clientId: selectedClientIdFromStorageOrDom() || null,
    forceRefresh,
  };
}

async function openWordstatView() {
  wordstatState.active = true;
  wordstatState.status = 'Проверяем подключение Wordstat...';
  wordstatState.error = '';
  ensureWordstatNav();
  renderWordstatPage();
  await loadWordstatConnection();
  wordstatState.status = wordstatState.connection?.configured ? 'Wordstat API готов. Можно загружать динамику.' : 'Wordstat API не готов: проверьте YANDEX_SEARCH_API_KEY / YANDEX_SEARCH_FOLDER_ID или OAuth.';
  renderWordstatPage();
}

async function submitWordstatForm(form) {
  const formData = new FormData(form);
  wordstatState.form = {
    phrases: String(formData.get('phrases') || '').trim(),
    period: String(formData.get('period') || 'WEEKLY'),
    fromDate: String(formData.get('fromDate') || ''),
    toDate: String(formData.get('toDate') || ''),
    regions: selectedRegionIdsFromForm(form),
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
  wordstatState.comparison = null;
  wordstatState.comparisonRange = null;
  wordstatState.status = `Отправляем batch-запрос: ${phrases.length} фраз.`;
  wordstatState.error = '';
  renderWordstatPage();

  try {
    const response = await apiFetch('/wordstat/dynamics/batch', { method: 'POST', body: JSON.stringify(collectRequestBody()) });
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

async function compareWordstatPeriod() {
  const range = previousPeriodRange();
  if (!range || !wordstatState.result) return;
  wordstatState.compareLoading = true;
  wordstatState.status = `Сравниваем с предыдущим периодом: ${range.fromDate} → ${range.toDate}.`;
  wordstatState.error = '';
  renderWordstatPage();
  try {
    const response = await apiFetch('/wordstat/dynamics/batch', { method: 'POST', body: JSON.stringify(collectRequestBody({ fromDate: range.fromDate, toDate: range.toDate, forceRefresh: false })) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Wordstat API не вернул сравнение');
    wordstatState.comparison = payload;
    wordstatState.comparisonRange = range;
    wordstatState.status = 'Сравнение с предыдущим периодом готово.';
  } catch (error) {
    if (error.message === 'Authentication required') return;
    wordstatState.error = error.message;
  } finally {
    wordstatState.compareLoading = false;
    renderWordstatPage();
  }
}

async function copyWordstatJson() {
  await navigator.clipboard?.writeText(JSON.stringify({ current: wordstatState.result || {}, comparison: wordstatState.comparison || null }, null, 2));
  wordstatState.status = 'JSON результата скопирован.';
  renderWordstatPage();
}

function mountWordstatExtension() {
  if (wordstatState.mounted) return;
  wordstatState.mounted = true;
  ensureWordstatNav();

  const observer = new MutationObserver(() => {
    ensureWordstatNav();
    if (wordstatState.active && !document.querySelector('[data-wordstat-form]')) renderWordstatPage();
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
    if (event.target.closest('[data-wordstat-compare]')) {
      await compareWordstatPeriod();
      return;
    }
    if (event.target.closest('[data-wordstat-copy-json]')) await copyWordstatJson();
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
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountWordstatExtension);
  else mountWordstatExtension();
}

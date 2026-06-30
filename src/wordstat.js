import { formatNumber, formatPercent } from './core/format.js';
import { escapeHtml } from './core/html.js';
import { getCurrentEmail, scopedStorageKey } from './core/storage.js';
import {
  buildWordstatTotalPoints,
  buildWordstatTotalSummary,
  calculateWordstatPercentDelta,
  createDefaultWordstatForm,
  createPreviousWordstatPeriodRange,
  createSelectedWordstatRegionIds,
  createWordstatRequestBody,
  fetchWordstatConnection,
  fetchWordstatDynamics,
  parseWordstatCustomRegions,
  parseWordstatPhrases,
  regionsSummary as summarizeWordstatRegions,
  WORDSTAT_LIMITS,
} from './features/wordstat/wordstat-legacy-adapter.js';

const WORDSTAT_VIEW_ID = 'wordstat';
const WORDSTAT_COLORS = ['#1677ff', '#16a34a', '#f97316', '#9333ea', '#dc2626', '#0891b2', '#4f46e5', '#65a30d'];
const WORDSTAT_REGION_TREE = [
  {
    id: '225',
    name: 'Россия',
    children: [
      {
        id: '1',
        name: 'Москва и область',
        children: [
          { id: '213', name: 'Москва' },
          { id: '10716', name: 'Балашиха' },
          { id: '10795', name: 'Видное' },
          { id: '21621', name: 'Воскресенск' },
          { id: '10758', name: 'Дмитров' },
          { id: '10725', name: 'Домодедово' },
          { id: '10738', name: 'Коломна' },
          { id: '10745', name: 'Королёв' },
          { id: '10747', name: 'Люберцы' },
          { id: '10750', name: 'Мытищи' },
          { id: '10765', name: 'Одинцово' },
          { id: '10754', name: 'Подольск' },
          { id: '10752', name: 'Химки' },
        ],
      },
      {
        id: '10174',
        name: 'Санкт-Петербург и Ленинградская область',
        children: [
          { id: '2', name: 'Санкт-Петербург' },
          { id: '969', name: 'Выборг' },
          { id: '10867', name: 'Гатчина' },
          { id: '10892', name: 'Кингисепп' },
        ],
      },
      {
        id: '1095',
        name: 'Краснодарский край',
        children: [
          { id: '35', name: 'Краснодар' },
          { id: '239', name: 'Сочи' },
          { id: '1107', name: 'Анапа' },
          { id: '10990', name: 'Геленджик' },
          { id: '1058', name: 'Новороссийск' },
        ],
      },
      { id: '43', name: 'Казань' },
      { id: '54', name: 'Екатеринбург' },
      { id: '65', name: 'Новосибирск' },
      { id: '39', name: 'Ростов-на-Дону' },
      { id: '172', name: 'Уфа' },
      { id: '51', name: 'Самара' },
      { id: '55', name: 'Пермь' },
      { id: '193', name: 'Воронеж' },
      { id: '47', name: 'Нижний Новгород' },
    ],
  },
];
const WORDSTAT_REGION_BY_ID = new Map();
collectRegions(WORDSTAT_REGION_TREE).forEach((region) => WORDSTAT_REGION_BY_ID.set(region.id, region));

const wordstatState = {
  mounted: false,
  active: false,
  loading: false,
  compareLoading: false,
  comparePanelOpen: false,
  regionModalOpen: false,
  regionDraftRegions: [],
  regionDraftCustom: '',
  expandedRegions: new Set(['225', '1', '10174', '1095']),
  status: '',
  error: '',
  connection: null,
  result: null,
  comparison: null,
  comparisonRange: null,
  form: defaultWordstatForm(),
};

function collectRegions(nodes) {
  return nodes.flatMap((node) => [node, ...collectRegions(node.children || [])]);
}

function defaultWordstatForm() {
  return createDefaultWordstatForm();
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

function parsePhrases(value) {
  return parseWordstatPhrases(value);
}

function parseCustomRegions(value) {
  return parseWordstatCustomRegions(value);
}

function selectedClientIdFromStorageOrDom() {
  const select = document.querySelector('[data-client-select]');
  if (select?.value) return select.value;
  const key = scopedStorageKey('directpilot_selected_client_id', getCurrentEmail());
  return window.localStorage.getItem(key) || '';
}

function allSelectedRegionIds() {
  return createSelectedWordstatRegionIds(wordstatState.form);
}

function regionLabel(id) {
  const region = WORDSTAT_REGION_BY_ID.get(String(id));
  return region ? `${region.name} (${region.id})` : String(id);
}

function regionsSummary(ids) {
  return summarizeWordstatRegions(ids, WORDSTAT_REGION_BY_ID);
}

function previousPeriodRange() {
  return createPreviousWordstatPeriodRange(wordstatState.form);
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
    wordstatState.connection = await fetchWordstatConnection();
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
  const selectedRegions = allSelectedRegionIds();
  const phrasesCount = parsePhrases(wordstatState.form.phrases).length;
  const totalPoints = result?.series?.reduce((sum, item) => sum + (item.points?.length || 0), 0) || 0;
  const completed = result?.meta?.completedPhrases ?? 0;
  const failed = result?.meta?.failedPhrases ?? 0;
  const defaultCompare = previousPeriodRange();
  if (!wordstatState.form.compareFromDate && defaultCompare) wordstatState.form.compareFromDate = defaultCompare.fromDate;
  if (!wordstatState.form.compareToDate && defaultCompare) wordstatState.form.compareToDate = defaultCompare.toDate;

  workspace.innerHTML = `
    <header class="appHeader">
      <div><span class="muted">Модуль спроса</span><h1>Спрос / Wordstat</h1></div>
      <div class="clientSelect"><span>Источник</span><strong>${connectionReady ? 'Wordstat готов' : 'Нужно подключение'}</strong><small>${escapeHtml(connection?.provider || 'yandex_search_api')}</small></div>
    </header>

    <section class="panel clientSourcePanel">
      <div><span class="muted">API</span><strong>${connectionReady ? 'Подключён' : 'Не готов'}</strong><small>${escapeHtml(connection?.message || 'Статус ещё не загружен')}</small></div>
      <div><span class="muted">Период</span><strong>${escapeHtml(wordstatState.form.period)}</strong><small>${escapeHtml(wordstatState.form.fromDate)} → ${escapeHtml(wordstatState.form.toDate)}</small></div>
      <div><span class="muted">Регионы</span><strong>${selectedRegions.length ? formatNumber(selectedRegions.length) : 'Все'}</strong><small>${escapeHtml(regionsSummary(selectedRegions))}</small></div>
      <div><span class="muted">Фразы</span><strong>${formatNumber(phrasesCount)}</strong><small>batch-запрос</small></div>
      <div><span class="muted">Точки</span><strong>${formatNumber(totalPoints)}</strong><small>из БД или API</small></div>
      <div><span class="muted">Успешно</span><strong>${formatNumber(completed)}</strong><small>ошибок: ${formatNumber(failed)}</small></div>
    </section>

    <div class="pageIntro">
      <span class="eyebrow">📈 Wordstat Dynamics</span>
      <h2>Динамика частотности по ключевым фразам</h2>
      <p>Выберите фразы, период и регион. Для нескольких фраз график рисует несколько линий, а таблицы показывают отдельные значения и сумму.</p>
    </div>

    <section class="panel">
      <form class="clientConnectForm" data-wordstat-form>
        <label class="authField" style="grid-column:1 / -1;"><span>Ключевые фразы, по одной на строку</span><textarea name="phrases" rows="6" placeholder="купить диван&#10;диван кровать">${escapeHtml(wordstatState.form.phrases)}</textarea></label>
        <label class="authField"><span>Группировка</span><select name="period"><option value="MONTHLY" ${wordstatState.form.period === 'MONTHLY' ? 'selected' : ''}>По месяцам</option><option value="WEEKLY" ${wordstatState.form.period === 'WEEKLY' ? 'selected' : ''}>По неделям</option><option value="DAILY" ${wordstatState.form.period === 'DAILY' ? 'selected' : ''}>По дням</option></select></label>
        <label class="authField"><span>Дата с</span><input type="date" name="fromDate" value="${escapeHtml(wordstatState.form.fromDate)}" /></label>
        <label class="authField"><span>Дата по</span><input type="date" name="toDate" value="${escapeHtml(wordstatState.form.toDate)}" /></label>
        <label class="authField"><span>Устройства</span><select name="devices"><option value="DEVICE_ALL" ${wordstatState.form.devices === 'DEVICE_ALL' ? 'selected' : ''}>Все</option><option value="DEVICE_DESKTOP" ${wordstatState.form.devices === 'DEVICE_DESKTOP' ? 'selected' : ''}>Desktop</option><option value="DEVICE_PHONE" ${wordstatState.form.devices === 'DEVICE_PHONE' ? 'selected' : ''}>Phone</option><option value="DEVICE_TABLET" ${wordstatState.form.devices === 'DEVICE_TABLET' ? 'selected' : ''}>Tablet</option></select></label>
        <label class="authField"><span>Кэш</span><select name="forceRefresh"><option value="false" ${!wordstatState.form.forceRefresh ? 'selected' : ''}>Использовать кэш</option><option value="true" ${wordstatState.form.forceRefresh ? 'selected' : ''}>Принудительно обновить</option></select></label>
        <div class="authField" style="grid-column:1 / -1;"><span>Регионы</span><div class="heroActions"><button class="secondaryButton" type="button" data-wordstat-open-region-modal>Выбрать регионы</button><strong>${escapeHtml(regionsSummary(selectedRegions))}</strong></div><small>Если ничего не выбрано, запрос уходит по всем регионам. Можно выбрать как в Wordstat: дерево регионов, города и области.</small></div>
        <div class="heroActions" style="grid-column:1 / -1;">
          <button class="approveButton" type="submit" ${wordstatState.loading ? 'disabled' : ''}>${wordstatState.loading ? 'Загружаем...' : 'Получить динамику'}</button>
          <button class="secondaryButton" type="button" data-wordstat-toggle-compare ${!result ? 'disabled' : ''}>Сравнить</button>
          ${result ? '<button class="secondaryButton" type="button" data-wordstat-copy-json>Скопировать JSON</button>' : ''}
        </div>
        ${wordstatState.comparePanelOpen ? renderCompareControls() : ''}
      </form>
      ${wordstatState.status ? `<div class="authStatus integrationStatus">${escapeHtml(wordstatState.status)}</div>` : ''}
      ${wordstatState.error ? `<div class="authStatus aiError">${escapeHtml(wordstatState.error)}</div>` : ''}
    </section>

    ${renderWordstatLimitsPanel(phrasesCount, selectedRegions.length)}
    ${result ? renderWordstatResult(result) : renderWordstatEmptyState()}
    ${wordstatState.regionModalOpen ? renderRegionModal() : ''}
  `;
}

function renderCompareControls() {
  return `
    <section class="panel" style="grid-column:1 / -1; margin:8px 0 0;">
      <div class="panelHeader"><div><h3>Период сравнения</h3><p>Укажи даты вручную. На графике текущий период будет сплошной линией, сравнение — пунктиром.</p></div><span class="aiStatusBadge pending">compare</span></div>
      <div class="clientSettingsGrid">
        <label class="authField"><span>Сравнить с даты</span><input type="date" name="compareFromDate" value="${escapeHtml(wordstatState.form.compareFromDate)}" /></label>
        <label class="authField"><span>Сравнить по дату</span><input type="date" name="compareToDate" value="${escapeHtml(wordstatState.form.compareToDate)}" /></label>
      </div>
      <div class="heroActions"><button class="approveButton" type="button" data-wordstat-run-compare ${wordstatState.compareLoading ? 'disabled' : ''}>${wordstatState.compareLoading ? 'Сравниваем...' : 'Загрузить сравнение'}</button><button class="secondaryButton" type="button" data-wordstat-fill-previous-period>Предыдущий период автоматически</button></div>
    </section>
  `;
}

function renderWordstatLimitsPanel(phrasesCount, regionsCount) {
  const apiRequests = phrasesCount || 0;
  const compareRequests = wordstatState.comparePanelOpen ? apiRequests : 0;
  return `
    <section class="panel">
      <div class="panelHeader"><div><h3>Лимиты и ограничения</h3><p>Yandex API не отдаёт остаток дневного лимита, поэтому показываем расчёт нагрузки и известные ограничения запроса.</p></div><span class="aiStatusBadge pending">limits</span></div>
      <div class="kpiGrid">
        <article class="kpi blue"><span>Запросов к API</span><strong>${formatNumber(apiRequests + compareRequests)}</strong></article>
        <article class="kpi green"><span>Фраз в batch</span><strong>${formatNumber(phrasesCount)} / ${WORDSTAT_LIMITS.maxPhrasesPerBatch}</strong></article>
        <article class="kpi orange"><span>Регионов</span><strong>${formatNumber(regionsCount)} / ${WORDSTAT_LIMITS.maxRegions}</strong></article>
      </div>
      <p class="mutedText">Ограничения: фраза до ${WORDSTAT_LIMITS.maxPhraseLength} символов, регионов до ${WORDSTAT_LIMITS.maxRegions}, устройств до ${WORDSTAT_LIMITS.maxDevices}. При превышении квоты Яндекс вернёт 429 или 503, точный остаток лимита в ответе API не приходит.</p>
      ${renderQuotaWarnings()}
    </section>
  `;
}

function renderQuotaWarnings() {
  const errors = [...(wordstatState.result?.series || []), ...(wordstatState.comparison?.series || [])]
    .map((item) => item.error || '')
    .filter((error) => error.includes('429') || error.includes('503'));
  if (!errors.length) return '';
  return `<div class="authStatus aiError">Есть ошибки лимитов: ${escapeHtml(errors[0])}</div>`;
}

function renderRegionModal() {
  const current = allSelectedRegionIds();
  const draft = [...new Set([...wordstatState.regionDraftRegions, ...parseCustomRegions(wordstatState.regionDraftCustom)])];
  return `
    <div style="position:fixed;inset:0;z-index:50;background:rgba(15,23,42,.35);display:flex;align-items:center;justify-content:center;padding:24px;">
      <section class="panel" style="width:min(560px,96vw);max-height:86vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 24px 70px rgba(15,23,42,.35);">
        <div class="panelHeader"><div><h3>Регионы</h3><p>Предыдущий выбор: ${escapeHtml(regionsSummary(current))}</p><p>Текущий выбор: ${escapeHtml(regionsSummary(draft))}</p></div><button class="secondaryButton" type="button" data-wordstat-close-region-modal>×</button></div>
        <div style="overflow:auto;padding:8px 4px 12px;max-height:52vh;">
          <label style="display:flex;gap:8px;align-items:center;margin:8px 0;"><input type="checkbox" data-wordstat-region-all ${!draft.length ? 'checked' : ''}/> Все регионы</label>
          ${WORDSTAT_REGION_TREE.map((node) => renderRegionTreeNode(node, 0)).join('')}
        </div>
        <label class="authField"><span>Другие коды регионов через запятую</span><input data-wordstat-region-custom value="${escapeHtml(wordstatState.regionDraftCustom)}" placeholder="Например: 977, 11029" /></label>
        <div class="heroActions" style="justify-content:center;"><button class="approveButton" type="button" data-wordstat-apply-regions>Подтвердить</button><button class="secondaryButton" type="button" data-wordstat-clear-regions>Все регионы</button></div>
      </section>
    </div>
  `;
}

function renderRegionTreeNode(node, level) {
  const hasChildren = Boolean(node.children?.length);
  const expanded = wordstatState.expandedRegions.has(node.id);
  const checked = wordstatState.regionDraftRegions.includes(node.id);
  return `
    <div style="margin-left:${level * 20}px;">
      <div style="display:flex;align-items:center;gap:6px;margin:6px 0;">
        ${hasChildren ? `<button type="button" class="secondaryButton" style="padding:2px 8px;min-width:28px;" data-wordstat-toggle-region-node="${escapeHtml(node.id)}">${expanded ? '−' : '+'}</button>` : '<span style="width:28px;"></span>'}
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;"><input type="checkbox" data-wordstat-region-modal value="${escapeHtml(node.id)}" ${checked ? 'checked' : ''}/><span>${escapeHtml(node.name)} <small class="muted">${escapeHtml(node.id)}</small></span></label>
      </div>
      ${hasChildren && expanded ? node.children.map((child) => renderRegionTreeNode(child, level + 1)).join('') : ''}
    </div>
  `;
}

function renderWordstatEmptyState() {
  return `<section class="panel emptyStatePanel compact"><h3>Данных пока нет</h3><p>Запустите batch-запрос. Тут появятся график с tooltip, сравнение, суммы и детализация.</p></section>`;
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
  const width = 1100;
  const height = 420;
  const padding = { left: 72, right: 32, top: 24, bottom: 62 };
  const comparisonSeries = (comparison?.series || []).filter((item) => !item.error && item.points?.length);
  const allValues = [...series, ...comparisonSeries].flatMap((item) => item.points.map((point) => Number(point.count || 0)));
  const maxY = Math.max(1, ...allValues);
  const maxLen = Math.max(1, ...series.map((item) => item.points.length), ...comparisonSeries.map((item) => item.points.length));
  const x = (index) => padding.left + (index / Math.max(1, maxLen - 1)) * (width - padding.left - padding.right);
  const y = (count) => padding.top + (1 - Number(count || 0) / maxY) * (height - padding.top - padding.bottom);
  const polyline = (points) => points.map((point, index) => `${x(index)},${y(point.count)}`).join(' ');
  const pointCircles = (item, index, isComparison = false) => item.points.map((point, pointIndex) => {
    const tooltip = `${isComparison ? 'Сравнение · ' : ''}${item.phrase}\n${periodLabel(point.date)}\n${formatNumber(point.count)} запросов`;
    return `<circle cx="${x(pointIndex)}" cy="${y(point.count)}" r="5" fill="${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]}" stroke="#fff" stroke-width="2" data-wordstat-chart-point data-tooltip="${escapeHtml(tooltip)}"/>`;
  }).join('');
  const firstSeries = series[0]?.points || [];
  return `
    <section class="panel"><div class="panelHeader"><div><h3>График динамики</h3><p>Наведи курсор на точку, чтобы увидеть дату, ключевую фразу и количество запросов.</p></div><span class="aiStatusBadge ready">hover</span></div>
      <div style="overflow:auto;"><svg viewBox="0 0 ${width} ${height}" style="min-width:860px;width:100%;height:auto;background:#fff;border-radius:18px;">
        ${[0, 0.25, 0.5, 0.75, 1].map((tick) => `<line x1="${padding.left}" y1="${y(maxY * tick)}" x2="${width - padding.right}" y2="${y(maxY * tick)}" stroke="#d8e0ec"/><text x="14" y="${y(maxY * tick) + 4}" font-size="12" fill="#1677ff">${formatNumber(Math.round(maxY * tick))}</text>`).join('')}
        ${firstSeries.map((point, index) => index % Math.ceil(firstSeries.length / 8 || 1) === 0 ? `<text x="${x(index) - 18}" y="${height - 26}" font-size="12" fill="#64748b">${escapeHtml(shortDateLabel(point.date))}</text><line x1="${x(index)}" y1="${height - padding.bottom}" x2="${x(index)}" y2="${height - padding.bottom + 8}" stroke="#94a3b8"/>` : '').join('')}
        ${series.map((item, index) => `<polyline points="${polyline(item.points)}" fill="none" stroke="${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`).join('')}
        ${comparisonSeries.map((item, index) => `<polyline points="${polyline(item.points)}" fill="none" stroke="${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]}" stroke-width="3" stroke-dasharray="8 8" opacity="0.7" stroke-linecap="round" stroke-linejoin="round"/>`).join('')}
        ${series.map((item, index) => pointCircles(item, index)).join('')}
        ${comparisonSeries.map((item, index) => pointCircles(item, index, true)).join('')}
        <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="#94a3b8"/>
      </svg></div>
      <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;">${series.map((item, index) => `<span><i style="display:inline-block;width:18px;height:4px;background:${WORDSTAT_COLORS[index % WORDSTAT_COLORS.length]};vertical-align:middle;margin-right:6px;"></i>${escapeHtml(item.phrase)}</span>`).join('')}${comparison ? '<span><i style="display:inline-block;width:18px;height:0;border-top:4px dashed #64748b;vertical-align:middle;margin-right:6px;"></i>пунктир = период сравнения</span>' : ''}</div>
    </section>
  `;
}

function periodLabel(date) {
  if (wordstatState.form.period === 'MONTHLY') return `Месяц: ${date}`;
  if (wordstatState.form.period === 'WEEKLY') return `Неделя с ${date}`;
  return `Дата: ${date}`;
}

function shortDateLabel(date) {
  const parsed = parseInputDate(date);
  if (!parsed) return date;
  return parsed.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function renderComparisonPanel(current, previous) {
  const currentByPhrase = new Map((current.summary?.phrases || []).map((item) => [item.phrase, item]));
  const previousByPhrase = new Map((previous.summary?.phrases || []).map((item) => [item.phrase, item]));
  const phrases = [...new Set([...currentByPhrase.keys(), ...previousByPhrase.keys()])];
  return `
    <section class="panel"><div class="panelHeader"><div><h3>Сравнение с выбранным периодом</h3><p>${escapeHtml(wordstatState.comparisonRange?.fromDate || '—')} → ${escapeHtml(wordstatState.comparisonRange?.toDate || '—')}</p></div><span class="aiStatusBadge ready">compare</span></div>
      <div class="tableWrap"><table><thead><tr><th>Фраза</th><th>Текущий период</th><th>Период сравнения</th><th>Разница</th><th>%</th></tr></thead><tbody>
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
  return `<details class="aiToolTrace" open><summary>${escapeHtml(series.phrase)} · ${formatNumber(points.length)} точек · ${escapeHtml(series.source || '—')}</summary><div class="tableWrap"><table><thead><tr><th>Дата</th><th>Частотность</th><th>Share</th><th>MoM</th><th>YoY</th><th>Index</th></tr></thead><tbody>${points.map((point) => `<tr><td>${escapeHtml(point.date)}</td><td>${formatNumber(point.count)}</td><td>${point.share == null ? '—' : Number(point.share).toPrecision(4)}</td><td>${formatPercent(point.mom)}</td><td>${formatPercent(point.yoy)}</td><td>${point.index == null ? '—' : formatNumber(point.index)}</td></tr>`).join('')}</tbody></table></div></details>`;
}

function buildTotalPoints(result) {
  return buildWordstatTotalPoints(result);
}

function buildTotalSummary(result) {
  return buildWordstatTotalSummary(result);
}

function percentDelta(current, previous) {
  return calculateWordstatPercentDelta(current, previous);
}

function collectRequestBody({ fromDate = wordstatState.form.fromDate, toDate = wordstatState.form.toDate, forceRefresh = wordstatState.form.forceRefresh } = {}) {
  return createWordstatRequestBody(wordstatState.form, selectedClientIdFromStorageOrDom() || null, {
    fromDate,
    toDate,
    forceRefresh,
  });
}

function syncFormState(form) {
  const formData = new FormData(form);
  wordstatState.form.phrases = String(formData.get('phrases') || '').trim();
  wordstatState.form.period = String(formData.get('period') || 'WEEKLY');
  wordstatState.form.fromDate = String(formData.get('fromDate') || '');
  wordstatState.form.toDate = String(formData.get('toDate') || '');
  wordstatState.form.compareFromDate = String(formData.get('compareFromDate') || wordstatState.form.compareFromDate || '');
  wordstatState.form.compareToDate = String(formData.get('compareToDate') || wordstatState.form.compareToDate || '');
  wordstatState.form.devices = String(formData.get('devices') || 'DEVICE_ALL');
  wordstatState.form.forceRefresh = String(formData.get('forceRefresh') || 'false') === 'true';
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
  syncFormState(form);
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
    const payload = await fetchWordstatDynamics(collectRequestBody());
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
  const fromDate = wordstatState.form.compareFromDate;
  const toDate = wordstatState.form.compareToDate;
  if (!fromDate || !toDate || !wordstatState.result) return;
  wordstatState.compareLoading = true;
  wordstatState.status = `Сравниваем с периодом: ${fromDate} → ${toDate}.`;
  wordstatState.error = '';
  renderWordstatPage();
  try {
    wordstatState.comparison = await fetchWordstatDynamics(collectRequestBody({ fromDate, toDate, forceRefresh: false }));
    wordstatState.comparisonRange = { fromDate, toDate };
    wordstatState.status = 'Сравнение готово.';
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

function showChartTooltip(event) {
  const point = event.target.closest?.('[data-wordstat-chart-point]');
  if (!point) return;
  let tooltip = document.querySelector('[data-wordstat-tooltip]');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.dataset.wordstatTooltip = 'true';
    tooltip.style.cssText = 'position:fixed;z-index:80;pointer-events:none;background:#fff;border:1px solid #d8e0ec;border-radius:12px;box-shadow:0 16px 36px rgba(15,23,42,.22);padding:10px 12px;font:13px system-ui;color:#0f172a;white-space:pre-line;';
    document.body.appendChild(tooltip);
  }
  tooltip.textContent = point.dataset.tooltip || '';
  tooltip.style.left = `${event.clientX + 14}px`;
  tooltip.style.top = `${event.clientY + 14}px`;
  tooltip.style.display = 'block';
}

function hideChartTooltip() {
  const tooltip = document.querySelector('[data-wordstat-tooltip]');
  if (tooltip) tooltip.style.display = 'none';
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

  document.addEventListener('mousemove', showChartTooltip);
  document.addEventListener('mouseout', (event) => {
    if (event.target.closest?.('[data-wordstat-chart-point]')) hideChartTooltip();
  });

  document.addEventListener('input', (event) => {
    if (event.target.matches('[data-wordstat-region-custom]')) {
      wordstatState.regionDraftCustom = event.target.value;
    }
    if (event.target.matches('[name="compareFromDate"]')) wordstatState.form.compareFromDate = event.target.value;
    if (event.target.matches('[name="compareToDate"]')) wordstatState.form.compareToDate = event.target.value;
  });

  document.addEventListener('change', (event) => {
    if (event.target.matches('[data-wordstat-region-modal]')) {
      const value = event.target.value;
      wordstatState.regionDraftRegions = event.target.checked
        ? [...new Set([...wordstatState.regionDraftRegions, value])]
        : wordstatState.regionDraftRegions.filter((id) => id !== value);
      renderWordstatPage();
    }
    if (event.target.matches('[data-wordstat-region-all]')) {
      wordstatState.regionDraftRegions = [];
      wordstatState.regionDraftCustom = '';
      renderWordstatPage();
    }
  });

  document.addEventListener('click', async (event) => {
    const navButton = event.target.closest('[data-wordstat-view]');
    if (navButton) {
      event.preventDefault();
      await openWordstatView();
      return;
    }
    if (event.target.closest('[data-wordstat-open-region-modal]')) {
      wordstatState.regionDraftRegions = [...(wordstatState.form.regions || [])];
      wordstatState.regionDraftCustom = wordstatState.form.customRegions || '';
      wordstatState.regionModalOpen = true;
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-close-region-modal]')) {
      wordstatState.regionModalOpen = false;
      renderWordstatPage();
      return;
    }
    const toggleNode = event.target.closest('[data-wordstat-toggle-region-node]');
    if (toggleNode) {
      const id = toggleNode.dataset.wordstatToggleRegionNode;
      if (wordstatState.expandedRegions.has(id)) wordstatState.expandedRegions.delete(id);
      else wordstatState.expandedRegions.add(id);
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-clear-regions]')) {
      wordstatState.regionDraftRegions = [];
      wordstatState.regionDraftCustom = '';
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-apply-regions]')) {
      wordstatState.form.regions = [...new Set(wordstatState.regionDraftRegions)];
      wordstatState.form.customRegions = wordstatState.regionDraftCustom;
      wordstatState.regionModalOpen = false;
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-toggle-compare]')) {
      wordstatState.comparePanelOpen = !wordstatState.comparePanelOpen;
      const range = previousPeriodRange();
      if (range && !wordstatState.form.compareFromDate) wordstatState.form.compareFromDate = range.fromDate;
      if (range && !wordstatState.form.compareToDate) wordstatState.form.compareToDate = range.toDate;
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-fill-previous-period]')) {
      const range = previousPeriodRange();
      if (range) {
        wordstatState.form.compareFromDate = range.fromDate;
        wordstatState.form.compareToDate = range.toDate;
      }
      renderWordstatPage();
      return;
    }
    if (event.target.closest('[data-wordstat-run-compare]')) {
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

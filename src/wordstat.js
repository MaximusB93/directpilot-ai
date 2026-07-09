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
import {
  compareWordstatPeriodFlow,
  copyWordstatJsonFlow,
  openWordstatFlow,
  submitWordstatDynamicsFlow,
} from './features/wordstat/wordstat-controller.js';
import { createWordstatPageRenderers } from './features/wordstat/wordstat-page.js';
import { createWordstatEventHandlers } from './features/wordstat/wordstat-events.js';
import './wordstat_date_fix.js';
import './wordstat_regions_patch.js';
import './wordstat_ai_chat.js';
import './wordstat_chart_hover.js';

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

let wordstatAutoOpening = false;

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
  const button = document.querySelector('[data-wordstat-view]');
  if (button) button.classList.toggle('active', Boolean(active));
}

function renderWordstatPage() {
  if (document.body.dataset.view !== WORDSTAT_VIEW_ID) return;
  const workspace = document.querySelector('.workspace');
  if (!workspace) return;
  wordstatState.active = true;
  setWordstatNavActive(true);

  const result = wordstatState.result;
  const connection = wordstatState.connection;
  const connectionReady = Boolean(connection?.configured);
  const selectedRegions = allSelectedRegionIds();
  const defaultCompare = previousPeriodRange();
  if (!wordstatState.form.compareFromDate && defaultCompare) wordstatState.form.compareFromDate = defaultCompare.fromDate;
  if (!wordstatState.form.compareToDate && defaultCompare) wordstatState.form.compareToDate = defaultCompare.toDate;

  workspace.innerHTML = `
    <header class="appHeader">
      <div><span class="muted">Модуль спроса</span><h1>Спрос / Wordstat</h1></div>
      <div class="wordstatConnectionState ${connectionReady ? 'is-ready' : 'is-pending'}">
        <span class="wordstatConnectionDot" aria-hidden="true"></span>
        <div><small>Wordstat API</small><strong>${connectionReady ? 'Подключён' : 'Не подключён'}</strong></div>
      </div>
    </header>

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

    ${result ? renderWordstatResult(result) : renderWordstatEmptyState()}
    ${wordstatState.regionModalOpen ? renderRegionModal() : ''}
  `;
}

const wordstatPageRenderers = createWordstatPageRenderers({
  state: wordstatState,
  escapeHtml,
  formatNumber,
  formatPercent,
  WORDSTAT_LIMITS,
  WORDSTAT_COLORS,
  WORDSTAT_REGION_TREE,
  allSelectedRegionIds,
  parseCustomRegions,
  regionsSummary,
  buildTotalPoints: buildWordstatTotalPoints,
  buildTotalSummary: buildWordstatTotalSummary,
  parseInputDate,
  percentDelta: calculateWordstatPercentDelta,
});

const {
  renderCompareControls,
  renderRegionModal,
  renderWordstatEmptyState,
  renderWordstatResult,
} = wordstatPageRenderers;

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
  await openWordstatFlow({
    state: wordstatState,
    ensureNav: () => {},
    render: renderWordstatPage,
    loadConnection: fetchWordstatConnection,
  });
}

async function submitWordstatForm(form) {
  await submitWordstatDynamicsFlow({
    state: wordstatState,
    form,
    syncFormState,
    parsePhrases,
    loadDynamics: (overrides) => fetchWordstatDynamics(collectRequestBody(overrides)),
    render: renderWordstatPage,
  });
}

async function compareWordstatPeriod() {
  await compareWordstatPeriodFlow({
    state: wordstatState,
    loadDynamics: (overrides) => fetchWordstatDynamics(collectRequestBody(overrides)),
    render: renderWordstatPage,
  });
}

async function copyWordstatJson() {
  await copyWordstatJsonFlow({
    state: wordstatState,
    copyText: (text) => navigator.clipboard?.writeText(text),
    render: renderWordstatPage,
  });
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

function shouldAutoOpenWordstatView() {
  return document.body.dataset.view === WORDSTAT_VIEW_ID && !document.querySelector('[data-wordstat-form]');
}

async function autoOpenWordstatView() {
  if (wordstatAutoOpening || wordstatState.active || !shouldAutoOpenWordstatView()) return;
  wordstatAutoOpening = true;
  try {
    await openWordstatView();
  } finally {
    wordstatAutoOpening = false;
  }
}

const wordstatEventHandlers = createWordstatEventHandlers({
  state: wordstatState,
  render: renderWordstatPage,
  openView: openWordstatView,
  submitForm: submitWordstatForm,
  comparePeriod: compareWordstatPeriod,
  copyJson: copyWordstatJson,
  previousPeriodRange,
  setNavActive: setWordstatNavActive,
  showTooltip: showChartTooltip,
  hideTooltip: hideChartTooltip,
});

function mountWordstatExtension() {
  if (wordstatState.mounted) return;
  wordstatState.mounted = true;

  const observer = new MutationObserver(() => {
    if (document.body.dataset.view !== WORDSTAT_VIEW_ID) return;
    void autoOpenWordstatView();
    if (wordstatState.active && !document.querySelector('[data-wordstat-form]')) renderWordstatPage();
  });
  observer.observe(document.body, { childList: true, subtree: true });
  void autoOpenWordstatView();

  document.addEventListener('mousemove', wordstatEventHandlers.handleMouseMoveEvent);
  document.addEventListener('mouseout', wordstatEventHandlers.handleMouseOutEvent);
  document.addEventListener('input', wordstatEventHandlers.handleInputEvent);
  document.addEventListener('change', wordstatEventHandlers.handleChangeEvent);
  document.addEventListener('click', wordstatEventHandlers.handleClickEvent);
  document.addEventListener('click', wordstatEventHandlers.handleRouteClickEvent, true);
  document.addEventListener('submit', wordstatEventHandlers.handleSubmitEvent);
}

if (document.body.dataset.page === 'app') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountWordstatExtension);
  else mountWordstatExtension();
}

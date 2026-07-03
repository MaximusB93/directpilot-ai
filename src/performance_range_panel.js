import { getCurrentEmail, scopedStorageKey } from './core/storage.js';

function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');
  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') return 'http://localhost:8000/api/v1';
  if (hostname === 'maximusb93.github.io') return 'https://directpilot-ai.vercel.app/api/v1';
  return `${origin}/api/v1`;
}

function sessionToken() {
  return window.localStorage.getItem('directpilot_session') || '';
}

async function periodApiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = sessionToken();
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

function escapeHtmlLocal(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatNumber(value, digits = 0) {
  const number = Number(value || 0);
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits, minimumFractionDigits: digits && number % 1 ? 1 : 0 }).format(number);
}

function formatMoney(value) {
  if (value == null) return '—';
  return `${formatNumber(value, 0)} ₽`;
}

function formatPercent(value) {
  if (value == null) return '—';
  return `${formatNumber(value, 2)}%`;
}

function selectedClientId() {
  const selectedFromDom = document.querySelector('[data-client-select]')?.value || '';
  if (selectedFromDom) return selectedFromDom;
  return window.localStorage.getItem(scopedStorageKey('directpilot_selected_client_id', getCurrentEmail())) || '';
}

function periodState() {
  window.__directPilotPeriodSummary = window.__directPilotPeriodSummary || {
    preset: 'yesterday',
    dateFrom: '',
    dateTo: '',
    loading: false,
    aiLoading: false,
    summary: null,
    analysis: null,
    error: '',
  };
  return window.__directPilotPeriodSummary;
}

function periodLabel(period) {
  if (!period) return '—';
  const presetLabel = {
    yesterday: 'Вчера',
    '7d': '7 дней',
    '14d': '14 дней',
    '30d': '30 дней',
    custom: 'Произвольный период',
  }[period.preset] || period.preset;
  return `${presetLabel}: ${period.dateFrom} — ${period.dateTo}`;
}

function renderDelta(value) {
  if (value == null) return '<small>нет сравнения</small>';
  const sign = Number(value) > 0 ? '+' : '';
  const cls = Number(value) > 0 ? 'up' : Number(value) < 0 ? 'down' : 'flat';
  return `<small class="periodDelta ${cls}">${sign}${formatNumber(value, 1)}%</small>`;
}

function renderPeriodKpis(summary) {
  const totals = summary?.totals || {};
  const changes = summary?.changes || {};
  return `
    <div class="kpiGrid periodSummaryKpis">
      <article class="kpi green"><span>Расход</span><strong>${formatMoney(totals.cost)}</strong>${renderDelta(changes.costDeltaPct)}</article>
      <article class="kpi blue"><span>Показы</span><strong>${formatNumber(totals.impressions)}</strong>${renderDelta(changes.impressionsDeltaPct)}</article>
      <article class="kpi orange"><span>Клики</span><strong>${formatNumber(totals.clicks)}</strong>${renderDelta(changes.clicksDeltaPct)}</article>
      <article class="kpi green"><span>Конверсии по целям</span><strong>${formatNumber(totals.goalConversions, 2)}</strong>${renderDelta(changes.goalConversionsDeltaPct)}</article>
      <article class="kpi blue"><span>CPA по целям</span><strong>${formatMoney(totals.goalCpa)}</strong>${renderDelta(changes.goalCpaDeltaPct)}</article>
      <article class="kpi orange"><span>CR</span><strong>${formatPercent(totals.conversionRate)}</strong></article>
    </div>
  `;
}

function flagLabel(flag) {
  return {
    spend_without_conversions: 'Расход без конверсий',
    high_cpa: 'CPA выше цели',
    low_ctr: 'Низкий CTR',
    low_data: 'Мало данных',
    promising_campaign: 'Возможность',
    network_segment_check: 'Проверить РСЯ/сегменты',
    ok: 'OK',
  }[flag] || flag;
}

function renderCampaignRows(campaigns) {
  if (!campaigns?.length) return '<div class="emptyStatePanel compact"><h3>Нет кампаний за период</h3><p>Директ не вернул строки по выбранному диапазону.</p></div>';
  return `
    <div class="tableWrap">
      <table>
        <thead><tr><th>Кампания</th><th>Расход</th><th>Клики</th><th>CTR</th><th>Конверсии</th><th>CPA</th><th>Сигналы</th><th>Следующий уровень</th></tr></thead>
        <tbody>${campaigns.slice(0, 12).map((item) => `
          <tr>
            <td><strong>${escapeHtmlLocal(item.campaignName || '—')}</strong><br><small>${escapeHtmlLocal(item.severity || '—')}</small></td>
            <td>${formatMoney(item.cost)}</td>
            <td>${formatNumber(item.clicks)}</td>
            <td>${formatPercent(item.ctr)}</td>
            <td>${formatNumber(item.goalConversions, 2)}</td>
            <td>${formatMoney(item.goalCpa)}</td>
            <td>${(item.issueFlags || []).map(flagLabel).map(escapeHtmlLocal).join(', ')}</td>
            <td>${escapeHtmlLocal((item.drilldown?.nextLevel || []).slice(0, 4).join(', ') || '—')}</td>
          </tr>
        `).join('')}</tbody>
      </table>
    </div>
  `;
}

function renderAiAnalysis(analysis) {
  if (!analysis) return '';
  const searchRows = analysis.searchQueryDrilldown?.rows || 0;
  const candidates = analysis.searchQueryDrilldown?.candidateNegativeKeywords || 0;
  return `
    <section class="panel periodAiResultPanel">
      <div class="panelHeader">
        <div>
          <span class="eyebrow">AI-анализ периода</span>
          <h3>Разбор динамики и рекомендаций</h3>
          <p>${escapeHtmlLocal(periodLabel(analysis.period))} · поисковых запросов: ${formatNumber(searchRows)} · кандидатов в минус-слова: ${formatNumber(candidates)}</p>
        </div>
        <span class="aiStatusBadge ready">read-only</span>
      </div>
      <div class="aiMarkdownAnswer">${escapeHtmlLocal(analysis.answer || '').replaceAll('\n', '<br>')}</div>
    </section>
  `;
}

function renderPeriodPanel() {
  const state = periodState();
  const summary = state.summary;
  const period = summary?.period;
  return `
    <section class="panel performanceRangePanel" data-performance-range-panel>
      <div class="panelHeader">
        <div>
          <span class="eyebrow">Live Direct report</span>
          <h3>Сводка по выбранному периоду</h3>
          <p>Выберите диапазон, загрузите read-only данные из Яндекс.Директа, затем запустите AI-анализ динамики и рекомендаций.</p>
        </div>
        <span class="aiStatusBadge ${summary ? 'ready' : 'pending'}">${summary ? `Кампаний: ${formatNumber(summary.campaigns?.length || 0)}` : 'выберите период'}</span>
      </div>
      <div class="periodControls">
        <label class="authField">
          <span>Период</span>
          <select data-period-preset>
            <option value="yesterday" ${state.preset === 'yesterday' ? 'selected' : ''}>Вчера</option>
            <option value="7d" ${state.preset === '7d' ? 'selected' : ''}>Последние 7 дней</option>
            <option value="14d" ${state.preset === '14d' ? 'selected' : ''}>Последние 14 дней</option>
            <option value="30d" ${state.preset === '30d' ? 'selected' : ''}>Последние 30 дней</option>
            <option value="custom" ${state.preset === 'custom' ? 'selected' : ''}>Произвольный диапазон</option>
          </select>
        </label>
        <label class="authField ${state.preset === 'custom' ? '' : 'mutedControl'}">
          <span>С даты</span>
          <input type="date" data-period-from value="${escapeHtmlLocal(state.dateFrom)}" ${state.preset === 'custom' ? '' : 'disabled'} />
        </label>
        <label class="authField ${state.preset === 'custom' ? '' : 'mutedControl'}">
          <span>По дату</span>
          <input type="date" data-period-to value="${escapeHtmlLocal(state.dateTo)}" ${state.preset === 'custom' ? '' : 'disabled'} />
        </label>
        <div class="periodActions">
          <button class="approveButton" type="button" data-load-period-summary ${state.loading ? 'disabled' : ''}>${state.loading ? 'Загружаем...' : 'Загрузить данные'}</button>
          <button class="secondaryButton" type="button" data-run-period-ai ${!summary || state.aiLoading ? 'disabled' : ''}>${state.aiLoading ? 'AI анализирует...' : 'Сделать AI-анализ'}</button>
        </div>
      </div>
      ${state.error ? `<div class="authStatus aiError">${escapeHtmlLocal(state.error)}</div>` : ''}
      ${summary ? `
        <p class="periodSummaryCaption">${escapeHtmlLocal(periodLabel(period))} · цели: ${escapeHtmlLocal((summary.selectedGoalIds || []).join(', ') || 'не указаны')} · источник: ${escapeHtmlLocal(summary.source || '')}</p>
        ${renderPeriodKpis(summary)}
        <p>CTR: ${formatPercent(summary.totals?.ctr)} · CPC: ${formatMoney(summary.totals?.avgCpc)} · предыдущий период: ${escapeHtmlLocal(period?.previousDateFrom || '—')} — ${escapeHtmlLocal(period?.previousDateTo || '—')}</p>
        ${renderCampaignRows(summary.campaigns || [])}
      ` : '<div class="emptyStatePanel compact"><h3>Период ещё не загружен</h3><p>Нажмите «Загрузить данные», чтобы подтянуть live-отчёт Яндекс.Директа.</p></div>'}
      ${renderAiAnalysis(state.analysis)}
    </section>
  `;
}

function mountPeriodPanel() {
  const workspace = document.querySelector('.workspace');
  const contextPanel = document.querySelector('.clientSourcePanel');
  if (!workspace || !contextPanel || document.querySelector('[data-performance-range-panel]')) return;
  const wrapper = document.createElement('div');
  wrapper.innerHTML = renderPeriodPanel();
  contextPanel.insertAdjacentElement('afterend', wrapper.firstElementChild);
}

function rerenderPeriodPanel() {
  const panel = document.querySelector('[data-performance-range-panel]');
  if (!panel) return;
  const wrapper = document.createElement('div');
  wrapper.innerHTML = renderPeriodPanel();
  panel.replaceWith(wrapper.firstElementChild);
}

function periodQuery() {
  const state = periodState();
  const params = new URLSearchParams();
  params.set('preset', state.preset || 'yesterday');
  if (state.preset === 'custom') {
    params.set('date_from', state.dateFrom || '');
    params.set('date_to', state.dateTo || '');
  }
  return params;
}

async function loadPeriodSummary() {
  const state = periodState();
  const clientId = selectedClientId();
  if (!clientId) return;
  state.loading = true;
  state.error = '';
  state.analysis = null;
  rerenderPeriodPanel();
  try {
    const response = await periodApiFetch(`/clients/${encodeURIComponent(clientId)}/performance-range?${periodQuery().toString()}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось загрузить данные периода');
    state.summary = payload;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = false;
    rerenderPeriodPanel();
  }
}

async function runPeriodAiAnalysis() {
  const state = periodState();
  const clientId = selectedClientId();
  if (!clientId || !state.summary) return;
  state.aiLoading = true;
  state.error = '';
  rerenderPeriodPanel();
  try {
    const body = { preset: state.preset || '14d', max_tokens: 3500 };
    if (state.preset === 'custom') {
      body.date_from = state.dateFrom;
      body.date_to = state.dateTo;
    }
    const response = await periodApiFetch(`/clients/${encodeURIComponent(clientId)}/performance-range/ai-analysis`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось выполнить AI-анализ');
    state.analysis = payload;
    state.summary = payload.summary || state.summary;
  } catch (error) {
    state.error = error.message;
  } finally {
    state.aiLoading = false;
    rerenderPeriodPanel();
  }
}

document.addEventListener('change', (event) => {
  const state = periodState();
  if (event.target.matches('[data-period-preset]')) {
    state.preset = event.target.value;
    state.summary = null;
    state.analysis = null;
    state.error = '';
    rerenderPeriodPanel();
  }
  if (event.target.matches('[data-period-from]')) state.dateFrom = event.target.value;
  if (event.target.matches('[data-period-to]')) state.dateTo = event.target.value;
});

document.addEventListener('click', (event) => {
  if (event.target.closest('[data-load-period-summary]')) {
    loadPeriodSummary();
  }
  if (event.target.closest('[data-run-period-ai]')) {
    runPeriodAiAnalysis();
  }
});

const periodObserver = new MutationObserver(() => mountPeriodPanel());
periodObserver.observe(document.body, { childList: true, subtree: true });
mountPeriodPanel();

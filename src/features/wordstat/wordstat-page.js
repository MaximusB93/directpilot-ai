export function createWordstatPageRenderers({
  state,
  escapeHtml,
  formatNumber,
  formatPercent,
  WORDSTAT_LIMITS,
  WORDSTAT_COLORS,
  WORDSTAT_REGION_TREE,
  allSelectedRegionIds,
  parseCustomRegions,
  regionsSummary,
  buildTotalPoints,
  buildTotalSummary,
  parseInputDate,
  percentDelta,
} = {}) {
  if (!state) throw new Error('Wordstat state is required');
  if (typeof allSelectedRegionIds !== 'function') throw new Error('Wordstat allSelectedRegionIds dependency is required');
  if (typeof parseCustomRegions !== 'function') throw new Error('Wordstat parseCustomRegions dependency is required');
  if (typeof regionsSummary !== 'function') throw new Error('Wordstat regionsSummary dependency is required');
  if (typeof buildTotalPoints !== 'function') throw new Error('Wordstat buildTotalPoints dependency is required');
  if (typeof buildTotalSummary !== 'function') throw new Error('Wordstat buildTotalSummary dependency is required');
  if (typeof parseInputDate !== 'function') throw new Error('Wordstat parseInputDate dependency is required');
  if (typeof percentDelta !== 'function') throw new Error('Wordstat percentDelta dependency is required');

  escapeHtml = escapeHtml || ((value) => String(value ?? ''));
  formatNumber = formatNumber || ((value) => String(value ?? 0));
  formatPercent = formatPercent || ((value) => (value == null ? '—' : `${value}%`));
  WORDSTAT_LIMITS = WORDSTAT_LIMITS || {};
  WORDSTAT_COLORS = WORDSTAT_COLORS || ['#1677ff'];
  WORDSTAT_REGION_TREE = WORDSTAT_REGION_TREE || [];

  function renderCompareControls() {
    return `
      <section class="panel" style="grid-column:1 / -1; margin:8px 0 0;">
        <div class="panelHeader"><div><h3>Период сравнения</h3><p>Укажи даты вручную. На графике текущий период будет сплошной линией, сравнение — пунктиром.</p></div><span class="aiStatusBadge pending">compare</span></div>
        <div class="clientSettingsGrid">
          <label class="authField"><span>Сравнить с даты</span><input type="date" name="compareFromDate" value="${escapeHtml(state.form.compareFromDate)}" /></label>
          <label class="authField"><span>Сравнить по дату</span><input type="date" name="compareToDate" value="${escapeHtml(state.form.compareToDate)}" /></label>
        </div>
        <div class="heroActions"><button class="approveButton" type="button" data-wordstat-run-compare ${state.compareLoading ? 'disabled' : ''}>${state.compareLoading ? 'Сравниваем...' : 'Загрузить сравнение'}</button><button class="secondaryButton" type="button" data-wordstat-fill-previous-period>Предыдущий период автоматически</button></div>
      </section>
    `;
  }

  function renderWordstatLimitsPanel(phrasesCount, regionsCount) {
    const apiRequests = phrasesCount || 0;
    const compareRequests = state.comparePanelOpen ? apiRequests : 0;
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
    const errors = [...(state.result?.series || []), ...(state.comparison?.series || [])]
      .map((item) => item.error || '')
      .filter((error) => error.includes('429') || error.includes('503'));
    if (!errors.length) return '';
    return `<div class="authStatus aiError">Есть ошибки лимитов: ${escapeHtml(errors[0])}</div>`;
  }

  function renderRegionModal() {
    const current = allSelectedRegionIds();
    const draft = [...new Set([...state.regionDraftRegions, ...parseCustomRegions(state.regionDraftCustom)])];
    return `
      <div style="position:fixed;inset:0;z-index:50;background:rgba(15,23,42,.35);display:flex;align-items:center;justify-content:center;padding:24px;">
        <section class="panel" style="width:min(560px,96vw);max-height:86vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 24px 70px rgba(15,23,42,.35);">
          <div class="panelHeader"><div><h3>Регионы</h3><p>Предыдущий выбор: ${escapeHtml(regionsSummary(current))}</p><p>Текущий выбор: ${escapeHtml(regionsSummary(draft))}</p></div><button class="secondaryButton" type="button" data-wordstat-close-region-modal>×</button></div>
          <div style="overflow:auto;padding:8px 4px 12px;max-height:52vh;">
            <label style="display:flex;gap:8px;align-items:center;margin:8px 0;"><input type="checkbox" data-wordstat-region-all ${!draft.length ? 'checked' : ''}/> Все регионы</label>
            ${WORDSTAT_REGION_TREE.map((node) => renderRegionTreeNode(node, 0)).join('')}
          </div>
          <label class="authField"><span>Другие коды регионов через запятую</span><input data-wordstat-region-custom value="${escapeHtml(state.regionDraftCustom)}" placeholder="Например: 977, 11029" /></label>
          <div class="heroActions" style="justify-content:center;"><button class="approveButton" type="button" data-wordstat-apply-regions>Подтвердить</button><button class="secondaryButton" type="button" data-wordstat-clear-regions>Все регионы</button></div>
        </section>
      </div>
    `;
  }

  function renderRegionTreeNode(node, level) {
    const hasChildren = Boolean(node.children?.length);
    const expanded = state.expandedRegions.has(node.id);
    const checked = state.regionDraftRegions.includes(node.id);
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
      ${renderWordstatChart(result, state.comparison)}
      ${state.comparison ? renderComparisonPanel(result, state.comparison) : ''}
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
    if (state.form.period === 'MONTHLY') return `Месяц: ${date}`;
    if (state.form.period === 'WEEKLY') return `Неделя с ${date}`;
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
      <section class="panel"><div class="panelHeader"><div><h3>Сравнение с выбранным периодом</h3><p>${escapeHtml(state.comparisonRange?.fromDate || '—')} → ${escapeHtml(state.comparisonRange?.toDate || '—')}</p></div><span class="aiStatusBadge ready">compare</span></div>
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

  return {
    renderCompareControls,
    renderWordstatLimitsPanel,
    renderQuotaWarnings,
    renderRegionModal,
    renderRegionTreeNode,
    renderWordstatEmptyState,
    renderWordstatResult,
    renderPhraseSummaryTable,
    renderWordstatChart,
    renderComparisonPanel,
    renderComparisonTotalRow,
    renderTotalSeries,
    renderWordstatSeries,
    renderSeriesTable,
  };
}

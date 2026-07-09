import { groupJournalEntriesByDate } from './journal-store.js';

function fallbackEscapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

const SOURCE_LABELS = {
  ai: 'AI',
  optimization: 'Оптимизация',
  integration: 'Интеграции',
  sync: 'Синхронизация',
  business_context: 'Контекст бизнеса',
  client: 'Клиент',
  system: 'Система',
};

const CATEGORY_LABELS = {
  recommendation: 'Рекомендация',
  action: 'Действие',
  status: 'Статус',
  data_change: 'Изменение данных',
  error: 'Ошибка',
  note: 'Заметка',
};

const SEVERITY_LABELS = {
  info: 'Инфо',
  success: 'Успех',
  warning: 'Внимание',
  error: 'Ошибка',
};

export function createJournalPageRenderers({ escapeHtml = fallbackEscapeHtml } = {}) {
  function renderJournalPage(context = {}) {
    return `
      <section class="journalPage" data-journal-page>
        ${renderJournalFilters(context)}
        ${context.state?.error ? `<div class="alert alertError">${escapeHtml(context.state.error)}</div>` : ''}
        ${renderJournalTimeline(context)}
        ${renderJournalLoadMore(context)}
      </section>
    `;
  }

  function renderJournalFilters(context = {}) {
    const filters = context.state?.filters || {};
    return `
      <section class="panel" data-journal-filters>
        <div class="panelHeader">
          <div>
            <h3>Фильтры</h3>
            <p>Фильтруем только смысловые события, а не каждый чих интерфейса.</p>
          </div>
        </div>
        <div class="formGrid">
          ${renderSelect('source', 'Источник', filters.source, SOURCE_LABELS)}
          ${renderSelect('category', 'Категория', filters.category, CATEGORY_LABELS)}
          ${renderSelect('severity', 'Важность', filters.severity, SEVERITY_LABELS)}
          <label class="fieldGroup">
            <span>Тип события</span>
            <input name="type" value="${escapeHtml(filters.type || '')}" placeholder="optimization.action_status_changed" />
          </label>
          <label class="fieldGroup">
            <span>С даты</span>
            <input type="date" name="fromDate" value="${escapeHtml(filters.fromDate || '')}" />
          </label>
          <label class="fieldGroup">
            <span>По дату</span>
            <input type="date" name="toDate" value="${escapeHtml(filters.toDate || '')}" />
          </label>
        </div>
        <div class="formActions">
          <button class="primaryButton" type="button" data-journal-apply-filters>Применить</button>
          <button class="secondaryButton" type="button" data-journal-reset-filters>Сбросить</button>
          <button class="secondaryButton" type="button" data-journal-refresh>Обновить</button>
        </div>
      </section>
    `;
  }

  function renderJournalTimeline(context = {}) {
    const state = context.state || {};
    const entries = Array.isArray(state.items) ? state.items : [];
    if (state.loading && entries.length === 0) {
      return renderJournalLoadingState();
    }
    if (entries.length === 0) {
      return renderJournalEmptyState();
    }

    return `
      <section class="journalTimeline" data-journal-timeline>
        ${groupJournalEntriesByDate(entries).map(renderJournalDateGroup).join('')}
      </section>
    `;
  }

  function renderJournalDateGroup(group) {
    return `
      <article class="panel journalDateGroup">
        <div class="panelHeader">
          <div>
            <h3>${escapeHtml(group.label)}</h3>
            <p>${group.items.length} ${pluralize(group.items.length, ['событие', 'события', 'событий'])}</p>
          </div>
        </div>
        <div class="journalEntries">
          ${group.items.map(renderJournalEntry).join('')}
        </div>
      </article>
    `;
  }

  function renderJournalEntry(entry) {
    const sourceLabel = SOURCE_LABELS[entry.source] || entry.source;
    const categoryLabel = CATEGORY_LABELS[entry.category] || entry.category;
    const severityLabel = SEVERITY_LABELS[entry.severity] || entry.severity;
    const occurredTime = formatTime(entry.occurredAt);
    return `
      <article class="journalEntry journalEntry--${escapeHtml(entry.severity)}" data-journal-entry-id="${escapeHtml(entry.id)}">
        <div class="journalEntryMeta">
          <span>${escapeHtml(occurredTime)}</span>
          <span>${escapeHtml(sourceLabel)}</span>
          <span>${escapeHtml(categoryLabel)}</span>
          <span>${escapeHtml(severityLabel)}</span>
        </div>
        <div class="journalEntryBody">
          <h4>${escapeHtml(entry.title)}</h4>
          ${entry.summary ? `<p>${escapeHtml(entry.summary)}</p>` : ''}
          <div class="journalEntryDetails">
            <span>Автор: ${escapeHtml(entry.actor?.label || 'System')}</span>
            ${entry.entity ? `<span>Объект: ${escapeHtml(entry.entity.label)}</span>` : ''}
            <span>Тип: ${escapeHtml(entry.type)}</span>
          </div>
          ${renderJournalEntryDetailsPanel(entry)}
        </div>
      </article>
    `;
  }

  function renderJournalEntryDetailsPanel(entry) {
    const rows = [
      renderJournalJsonBlock('До', entry.before),
      renderJournalJsonBlock('После', entry.after),
      renderJournalJsonBlock('Метаданные', entry.metadata),
    ].filter(Boolean);

    if (rows.length === 0) {
      return `
        <details class="journalEntryMore" data-journal-entry-more>
          <summary>Подробнее</summary>
          <p class="muted">Для этой записи нет before / after / metadata. Бывает и такое: событие есть, драматургии нет.</p>
        </details>
      `;
    }

    return `
      <details class="journalEntryMore" data-journal-entry-more>
        <summary>Подробнее</summary>
        <div class="journalEntryJsonGrid">
          ${rows.join('')}
        </div>
      </details>
    `;
  }

  function renderJournalJsonBlock(label, value) {
    if (!hasUsefulDetails(value)) return '';
    return `
      <section class="journalEntryJsonBlock">
        <h5>${escapeHtml(label)}</h5>
        <pre><code>${escapeHtml(formatJson(value))}</code></pre>
      </section>
    `;
  }

  function renderJournalEmptyState() {
    return `
      <section class="emptyState" data-journal-empty>
        <h3>В журнале пока нет событий</h3>
        <p>Когда появятся AI-рекомендации, действия оптимизации, синхронизации или изменения контекста, они будут здесь.</p>
      </section>
    `;
  }

  function renderJournalLoadingState() {
    return `
      <section class="emptyState" data-journal-loading>
        <h3>Загружаем журнал</h3>
        <p>Ищем полезные события, а не просто шум ради красивой ленты.</p>
      </section>
    `;
  }

  function renderJournalLoadMore(context = {}) {
    const state = context.state || {};
    if (!state.nextCursor) return '';
    return `
      <div class="formActions" data-journal-load-more-panel>
        <button class="secondaryButton" type="button" data-journal-load-more ${state.loading ? 'disabled' : ''}>
          ${state.loading ? 'Загружаем...' : 'Загрузить ещё'}
        </button>
      </div>
    `;
  }

  function renderSelect(name, label, value, labels) {
    return `
      <label class="fieldGroup">
        <span>${escapeHtml(label)}</span>
        <select name="${escapeHtml(name)}">
          <option value="">Все</option>
          ${Object.entries(labels).map(([optionValue, optionLabel]) => `
            <option value="${escapeHtml(optionValue)}" ${value === optionValue ? 'selected' : ''}>${escapeHtml(optionLabel)}</option>
          `).join('')}
        </select>
      </label>
    `;
  }

  return {
    renderJournalPage,
    renderJournalFilters,
    renderJournalTimeline,
    renderJournalEntry,
    renderJournalEntryDetailsPanel,
    renderJournalJsonBlock,
    renderJournalEmptyState,
    renderJournalLoadMore,
  };
}

function formatTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function hasUsefulDetails(value) {
  if (!value || typeof value !== 'object') return false;
  if (Array.isArray(value)) return value.length > 0;
  return Object.keys(value).length > 0;
}

function formatJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (error) {
    return String(value ?? '');
  }
}

function pluralize(value, forms) {
  const abs = Math.abs(value) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

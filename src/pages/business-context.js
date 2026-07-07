import { renderEmptyState, renderPanel, renderStatusBadge } from '../components/index.js';

export const BUSINESS_CONTEXT_PAGE_ID = 'business-context';

export const businessContextPage = {
  id: BUSINESS_CONTEXT_PAGE_ID,
  title: 'Контекст бизнеса',
  description: 'Память проекта: ниша, продукт, аудитория, география, офферы, ограничения и заметки AI.',
};

export function businessContextPageContract() {
  return {
    routeId: BUSINESS_CONTEXT_PAGE_ID,
    requiredContext: [
      'selectedClientId',
      'selectedClient',
      'businessContext',
      'businessContextDraft',
      'businessContextLoading',
      'businessContextSaving',
      'businessContextStatus',
    ],
    legacyRenderer: 'renderBusinessContext',
    extractionStatus: 'content-composer-ready',
    componentPrimitives: [
      'renderPanel',
      'renderEmptyState',
      'renderStatusBadge',
    ],
    extractedBuilders: [
      'renderBusinessContextIntro',
      'renderBusinessContextPanel',
      'renderBusinessContextContent',
    ],
    nextStep: 'Start Wordstat store/service extraction after local validation path is ready.',
  };
}

function contextScoreTone(score = 0) {
  if (score >= 80) return 'success';
  if (score >= 40) return 'info';
  if (score > 0) return 'warning';
  return 'neutral';
}

function hasBusinessContextData(context = {}) {
  return Object.values(context || {}).some((value) => String(value || '').trim());
}

function renderBusinessContextStatus(message, { escapeHtml } = {}) {
  if (!message) return '';
  return `<div class="authStatus integrationStatus">${escapeHtml(message)}</div>`;
}

export function renderBusinessContextIntro({ escapeHtml }) {
  return `
    <div class="pageIntro">
      <span class="eyebrow">🧭 Контекст бизнеса</span>
      <h2>Память проекта для AI-аналитика</h2>
      <p>${escapeHtml('Заполните бизнес-контекст один раз, чтобы AI учитывал бренд, нишу, офферы, ограничения и нерелевантные темы при анализе кампаний и поисковых запросов.')}</p>
    </div>
  `;
}

export function renderBusinessContextPanel({
  compact = false,
  context = {},
  score = 0,
  copyText = '',
  businessContextLoading = false,
  businessContextSaving = false,
  businessContextStatus = '',
  escapeHtml,
}) {
  const isBusy = businessContextLoading || businessContextSaving;
  const field = (name, label, placeholder = '') => `
    <label class="authField businessContextField">
      <span>${escapeHtml(label)}</span>
      <textarea name="${name}" placeholder="${escapeHtml(placeholder)}" ${isBusy ? 'disabled' : ''}>${escapeHtml(context[name] || '')}</textarea>
    </label>
  `;
  const scoreBadge = renderStatusBadge({
    label: `Заполнено ${score}%`,
    tone: contextScoreTone(score),
    title: 'Оценка заполненности бизнес-контекста',
  });
  const emptyContext = !hasBusinessContextData(context);

  if (compact) {
    return renderPanel({
      title: 'Контекст бизнеса',
      subtitle: emptyContext
        ? 'AI пока не знает нишу, офферы, ограничения и нерелевантные темы.'
        : 'Бизнес-контекст заполнен и используется в AI-анализе.',
      className: 'businessContextPanel compactBusinessContext',
      actions: `<div class="panelActionsInline">${scoreBadge}<button class="secondaryButton" data-go-view="business-context">Открыть</button></div>`,
      children: `
        ${renderBusinessContextStatus(businessContextStatus, { escapeHtml })}
        ${emptyContext
          ? renderEmptyState({ title: 'Контекст не заполнен', description: 'Добавьте нишу, продукт, аудиторию, географию и ограничения, чтобы AI давал не общие советы, а рекомендации по проекту.' })
          : `<div class="insightGrid">
              <article><span>Ниша</span><strong>${escapeHtml(context.industry || 'не указана')}</strong></article>
              <article><span>География</span><strong>${escapeHtml(context.geography || 'не указана')}</strong></article>
              <article><span>Ограничения</span><strong>${escapeHtml(context.businessConstraints ? 'есть' : 'не указаны')}</strong></article>
            </div>`}
      `,
    });
  }

  return renderPanel({
    title: compact ? 'Контекст бизнеса для AI' : 'Контекст бизнеса',
    subtitle: compact ? 'AI учитывает эти данные при аудите и рекомендациях.' : 'Заполните информацию о бизнесе, чтобы AI не давал generic-рекомендации.',
    className: `businessContextPanel ${compact ? 'compactBusinessContext' : ''}`,
    actions: `<div class="panelActionsInline">${scoreBadge}</div>`,
    children: `
      ${renderBusinessContextStatus(businessContextStatus, { escapeHtml })}
      ${emptyContext ? renderEmptyState({ title: 'Контекст пока пустой', description: 'Заполните ключевые поля: нишу, продукт, аудиторию, географию и ограничения. AI без контекста превращается в генератор общих советов, а это мы уже видели и не скучаем.' }) : ''}
      <form class="businessContextForm" data-business-context-form>
        <div class="clientSettingsGrid businessContextGrid">
          ${field('companyName', 'Компания', 'Название клиента')}
          ${field('websiteUrl', 'Сайт', 'https://example.ru')}
          ${field('industry', 'Ниша', 'Например: медицина, недвижимость, e-commerce')}
          ${field('productDescription', 'Продукт / услуга', 'Что продаём и чем отличаемся')}
          ${field('targetAudience', 'Целевая аудитория', 'Кто покупает, сегменты, B2B/B2C')}
          ${field('geography', 'География', 'Города, регионы, ограничения доставки')}
          ${field('mainOffers', 'Основные офферы', 'Акции, преимущества, УТП')}
          ${field('conversionActions', 'Целевые действия', 'Заявка, звонок, бронь, покупка, квиз')}
          ${field('averageOrderValue', 'Средний чек / ценность лида', 'Средний чек, маржа, LTV или ценность заявки')}
          ${field('leadValueNotes', 'Заметки по ценности лида', 'Какие лиды качественные/некачественные')}
          ${field('businessConstraints', 'Ограничения бизнеса', 'Бюджет, склад, сроки, юридические ограничения')}
          ${field('negativeTopics', 'Нерелевантные темы / минус-направления', 'Запросы и темы, которые не подходят бизнесу')}
          ${field('landingPageNotes', 'Посадочные страницы и заметки', 'URL, структура, важные блоки. Автопроверки страниц пока нет.')}
          ${field('competitorNotes', 'Конкуренты', 'Конкуренты, отличие, ценовое позиционирование')}
          ${field('manualNotes', 'Ручные заметки специалиста', 'Что важно помнить при аудите и оптимизации')}
          ${field('memoryNotes', 'Память проекта', 'Сохранённые выводы AI и важные решения')}
          ${field('sourceNotes', 'Источники контекста', 'Откуда взята информация: клиент, бриф, звонок, CRM')}
        </div>
        <div class="authStatus integrationStatus">Автоматический анализ посадочных страниц будет добавлен отдельной итерацией. Сейчас контекст заполняется вручную.</div>
        <div class="heroActions">
          <button class="approveButton" type="submit" ${isBusy ? 'disabled' : ''}>${isBusy ? 'Сохраняем...' : 'Сохранить контекст'}</button>
          <button class="secondaryButton" type="button" data-reset-business-context>Очистить несохранённые изменения</button>
          <button class="secondaryButton" type="button" data-copy-text="${escapeHtml(copyText)}">Скопировать контекст</button>
        </div>
      </form>
    `,
  });
}

export function renderBusinessContextContent(context) {
  return `
    ${renderBusinessContextIntro(context)}
    ${renderBusinessContextPanel(context)}
  `;
}

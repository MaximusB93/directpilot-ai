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
    extractedBuilders: [
      'renderBusinessContextIntro',
      'renderBusinessContextPanel',
      'renderBusinessContextContent',
    ],
    nextStep: 'Wire integrations page content composer after business context is stable.',
  };
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
  const field = (name, label, placeholder = '') => `
    <label class="businessContextField">
      <span>${label}</span>
      <textarea name="${name}" placeholder="${escapeHtml(placeholder)}" ${businessContextLoading || businessContextSaving ? 'disabled' : ''}>${escapeHtml(context[name] || '')}</textarea>
    </label>
  `;

  return `
    <section class="panel businessContextPanel ${compact ? 'compactBusinessContext' : ''}">
      <div class="panelHeader">
        <div>
          <h3>${compact ? 'Контекст бизнеса для AI' : 'Контекст бизнеса'}</h3>
          <p>${compact ? 'AI учитывает эти данные при аудите и рекомендациях.' : 'Заполните информацию о бизнесе, чтобы AI не давал generic-рекомендации.'}</p>
        </div>
        <div class="contextScore"><span>Заполнено</span><strong>${score}%</strong></div>
      </div>
      ${businessContextStatus ? `<div class="authStatus integrationStatus">${escapeHtml(businessContextStatus)}</div>` : ''}
      <form class="businessContextForm" data-business-context-form>
        <div class="businessContextGrid">
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
          <button class="approveButton" type="submit" ${businessContextLoading ? 'disabled' : ''}>${businessContextLoading ? 'Сохраняем...' : 'Сохранить контекст'}</button>
          <button class="secondaryButton" type="button" data-reset-business-context>Очистить несохранённые изменения</button>
          <button class="secondaryButton" type="button" data-copy-text="${escapeHtml(copyText)}">Скопировать контекст</button>
        </div>
      </form>
    </section>
  `;
}

export function renderBusinessContextContent(context) {
  return `
    ${renderBusinessContextIntro(context)}
    ${renderBusinessContextPanel(context)}
  `;
}

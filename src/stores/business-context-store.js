const BUSINESS_CONTEXT_DATA_FIELDS = [
  'industry',
  'productDescription',
  'targetAudience',
  'geography',
  'mainOffers',
  'conversionActions',
  'businessConstraints',
];

const BUSINESS_CONTEXT_COMPLETENESS_FIELDS = [
  'industry',
  'productDescription',
  'targetAudience',
  'geography',
  'mainOffers',
  'conversionActions',
  'businessConstraints',
  'negativeTopics',
];

export function normalizeBusinessContext(payload = {}) {
  return {
    companyName: payload?.companyName ?? payload?.brandName ?? payload?.company_name ?? payload?.brand_name ?? '',
    websiteUrl: payload?.websiteUrl ?? payload?.website_url ?? '',
    industry: payload?.industry ?? payload?.businessNiche ?? payload?.business_niche ?? '',
    productDescription: payload?.productDescription ?? payload?.productSummary ?? payload?.product_description ?? payload?.product_summary ?? '',
    targetAudience: payload?.targetAudience ?? payload?.target_audience ?? '',
    geography: payload?.geography || '',
    seasonality: payload?.seasonality || '',
    mainOffers: payload?.mainOffers ?? payload?.main_offers ?? '',
    conversionActions: payload?.conversionActions ?? payload?.conversion_actions ?? '',
    averageOrderValue: payload?.averageOrderValue ?? payload?.average_order_value ?? '',
    leadValueNotes: payload?.leadValueNotes ?? payload?.lead_value_notes ?? '',
    businessConstraints: payload?.businessConstraints ?? payload?.business_constraints ?? '',
    negativeTopics: payload?.negativeTopics ?? payload?.negative_topics ?? '',
    landingPageNotes: payload?.landingPageNotes ?? payload?.landing_page_notes ?? '',
    competitorNotes: payload?.competitorNotes ?? payload?.competitor_notes ?? '',
    manualNotes: payload?.manualNotes ?? payload?.manual_notes ?? '',
    memoryNotes: payload?.memoryNotes ?? payload?.memory_notes ?? '',
    sourceNotes: payload?.sourceNotes ?? payload?.source_notes ?? '',
    updatedAt: payload?.updatedAt ?? payload?.updated_at ?? '',
  };
}

export function createBusinessContextPayload(context = {}) {
  return {
    brandName: context.companyName || '',
    businessNiche: context.industry || '',
    productSummary: context.productDescription || '',
    targetAudience: context.targetAudience || '',
    geography: context.geography || '',
    seasonality: context.seasonality || '',
    mainOffers: context.mainOffers || '',
    conversionActions: context.conversionActions || '',
    averageOrderValue: context.averageOrderValue || '',
    leadValueNotes: context.leadValueNotes || '',
    businessConstraints: context.businessConstraints || '',
    negativeTopics: context.negativeTopics || '',
    landingPageNotes: context.landingPageNotes || '',
    competitorNotes: context.competitorNotes || '',
    manualNotes: context.manualNotes || '',
    memoryNotes: context.memoryNotes || '',
    sourceNotes: context.sourceNotes || '',
  };
}

export function createDefaultBusinessContext(client = {}) {
  return normalizeBusinessContext({
    company_name: client.name || '',
    website_url: '',
    industry: client.segment || '',
  });
}

export function hasBusinessContextData(context) {
  if (!context) return false;
  return BUSINESS_CONTEXT_DATA_FIELDS.some((field) => String(context[field] || '').trim().length > 0);
}

export function createBusinessContextCopyText(context) {
  const rows = [
    ['Компания', context.companyName],
    ['Сайт', context.websiteUrl],
    ['Ниша', context.industry],
    ['Продукт', context.productDescription],
    ['ЦА', context.targetAudience],
    ['География', context.geography],
    ['Офферы', context.mainOffers],
    ['Целевые действия', context.conversionActions],
    ['Средний чек / ценность лида', context.averageOrderValue],
    ['Качественные лиды', context.leadValueNotes],
    ['Ограничения бизнеса', context.businessConstraints],
    ['Нерелевантные темы', context.negativeTopics],
    ['Посадочные страницы', context.landingPageNotes],
    ['Конкуренты', context.competitorNotes],
    ['Заметки специалиста', context.manualNotes],
    ['Память проекта', context.memoryNotes],
    ['Источники', context.sourceNotes],
  ];
  return rows.map(([label, value]) => `${label}: ${value || '—'}`).join('\n');
}

export function createBusinessContextDraftFromForm(form) {
  const formData = new FormData(form);
  return normalizeBusinessContext({
    company_name: formData.get('companyName'),
    website_url: formData.get('websiteUrl'),
    industry: formData.get('industry'),
    product_description: formData.get('productDescription'),
    target_audience: formData.get('targetAudience'),
    geography: formData.get('geography'),
    main_offers: formData.get('mainOffers'),
    conversion_actions: formData.get('conversionActions'),
    average_order_value: formData.get('averageOrderValue'),
    lead_value_notes: formData.get('leadValueNotes'),
    business_constraints: formData.get('businessConstraints'),
    negative_topics: formData.get('negativeTopics'),
    landing_page_notes: formData.get('landingPageNotes'),
    competitor_notes: formData.get('competitorNotes'),
    manual_notes: formData.get('manualNotes'),
    memory_notes: formData.get('memoryNotes'),
    source_notes: formData.get('sourceNotes'),
  });
}

export function createBusinessContextForAi(context, draft) {
  const sourceContext = context || draft;
  if (!hasBusinessContextData(sourceContext)) return null;
  return createBusinessContextPayload(sourceContext);
}

export function calculateBusinessContextCompletenessScore(context) {
  if (!context) return 0;
  const filled = BUSINESS_CONTEXT_COMPLETENESS_FIELDS.filter((field) => String(context[field] || '').trim().length > 0).length;
  return Math.round((filled / BUSINESS_CONTEXT_COMPLETENESS_FIELDS.length) * 100);
}

/**
 * One dictionary for every backend code the interface may need to show.
 *
 * Rule that makes this file worth having: if a code is not in the dictionary,
 * it is NOT printed. `labelFor` returns `null` for anything unknown, and the
 * callers turn that into a dash or drop the row. Printing the raw value as a
 * fallback is what let `direct_no_data`, `manual_review` and
 * `campaign_metadata_issue` leak onto the screen in the first place — every new
 * backend code would leak again the same way.
 *
 * Codes are grouped by context because the same short code means different
 * things in different places (`unavailable` is a source and a request status,
 * `not_applicable` is a status and a verification result).
 */

export const LABEL_GROUPS = Object.freeze({
  // Data slices requested from Yandex Direct (capabilities / dimensions).
  auditCapability: {
    campaigns: 'кампании',
    campaign_performance: 'эффективность кампаний',
    campaign_daily_dynamics: 'дневная динамика кампании',
    campaign_settings: 'настройки кампании',
    campaign_strategy: 'стратегия кампании',
    campaign_status: 'статус кампании',
    conversions_by_goal: 'конверсии по выбранным целям',
    goals: 'цели',
    search_queries: 'поисковые запросы',
    ad_groups: 'группы',
    ad_group_performance: 'эффективность групп',
    keywords: 'ключевые фразы',
    keyword_performance: 'эффективность ключевых фраз',
    autotargeting: 'автотаргетинг',
    bid_modifiers: 'корректировки ставок',
    ads: 'объявления и креативы',
    landing_pages: 'посадочные страницы',
    placements: 'площадки',
    audiences: 'аудитории',
    audience_targets: 'аудиторные таргетинги',
    audience_exclusions: 'исключения аудиторий',
    retargeting_lists: 'списки ретаргетинга',
    retargeting_segments: 'сегменты ретаргетинга',
    devices: 'устройства',
    geo: 'география',
    demographics: 'демография',
    frequency: 'частотность',
    conversion_sources: 'источники конверсий',
    lead_quality: 'качество лидов',
  },

  // Where a number came from.
  auditSource: {
    live: 'Live Яндекс.Директ',
    cached_live: 'Кеш live-данных',
    saved: 'Сохранённые данные',
    mixed: 'Смешанный источник',
    yandex_direct_live_report: 'Live-отчёт Директа',
    yandex_direct_live_service: 'Live API Директа',
    yandex_direct_cached_live: 'Кеш live-отчёта',
    direct_read_cache: 'Кеш DirectPilot',
    saved_campaign_stats: 'Сохранённая статистика',
    unavailable: 'Источник недоступен',
  },

  // Lifecycle of one data request.
  auditRequestStatus: {
    pending: 'Ожидает выполнения',
    queued: 'Ожидает выполнения',
    processing: 'В обработке',
    waiting_for_report_queue: 'Ожидает свободное место в очереди',
    offline_report_processing: 'Формируется отчёт',
    unavailable_after_retry_limit: 'Недоступно после повторных попыток',
    ready: 'Данные получены',
    completed: 'Данные получены',
    collected: 'Данные получены',
    cached: 'Получено из кеша',
    partial: 'Получены частично',
    insufficient_data: 'Недостаточно данных',
    unavailable: 'Источник недоступен',
    unsupported: 'Не поддерживается',
    failed: 'Ошибка получения',
    not_applicable: 'Неприменимо',
    rejected_by_validation: 'Отклонено backend-валидатором',
  },

  // Verification result of a hypothesis, in the feminine form used for «гипотеза».
  auditVerificationStatus: {
    confirmed: 'Подтверждена',
    partially_confirmed: 'Подтверждена частично',
    rejected: 'Отклонена',
    unverified: 'Не подтверждена',
    not_applicable: 'Неприменима',
    collecting_data: 'Собираем данные',
    proposed: 'Предложена',
  },

  // Verification result in the neuter form used for a finding.
  auditVerification: {
    confirmed: 'Подтверждено',
    partially_confirmed: 'Частично подтверждено',
    unverified: 'Не подтверждено',
    rejected: 'Опровергнуто',
    not_applicable: 'Неприменимо',
  },

  // What the investigation suspects.
  auditHypothesis: {
    search_query_waste: 'нерелевантные поисковые запросы',
    ad_group_concentration: 'концентрация расхода в группах',
    keyword_waste: 'неэффективные ключевые фразы',
    device_segment_gap: 'разрыв между устройствами',
    geo_segment_gap: 'разрыв между регионами',
    placement_waste: 'неэффективные площадки',
    retargeting_segment_issue: 'проблема сегмента ретаргетинга',
    tracking_issue: 'проблема отслеживания конверсий',
    campaign_metadata_issue: 'проблема настроек кампании',
  },

  // Why an investigation round stopped.
  auditStopReason: {
    next_level_requested: 'Запрошен следующий уровень детализации',
    sufficient_evidence_or_rejected: 'Доказательств достаточно',
    max_rounds_reached: 'Достигнут предел раундов',
    request_budget_reached: 'Исчерпан бюджет запросов',
    low_data: 'Мало статистики',
    unknown_conversion_metric: 'Нет надёжных данных о конверсиях',
  },

  // Detected signal on a campaign.
  auditSignal: {
    spend_without_goal_conversions: 'Расход без конверсий',
    cpa_above_target: 'CPA выше цели',
    goal_conversions_drop: 'Снижение конверсий',
    budget_spike: 'Рост расхода',
    low_ctr: 'Низкий CTR',
    high_cpc_traffic_proxy: 'Высокий CPC относительно кампаний-аналогов',
    traffic_metrics_reviewed: 'CTR и CPC проверены',
    traffic_metrics_available: 'CTR и CPC рассчитаны',
    conversion_data_unknown: 'Нет надёжных данных о конверсиях',
    low_data: 'Мало статистики',
    good_campaign: 'Эффективная кампания',
    stable_efficiency: 'Стабильная эффективность',
    campaign_health: 'Состояние кампании',
  },

  auditConversionState: {
    known_positive: 'Конверсии получены',
    known_zero: 'Подтверждённый 0',
    unknown: 'Метрика не получена',
    low_sample: 'Малая выборка',
    not_applicable: 'Нет показов в периоде',
  },

  auditAnalysisMode: {
    conversion_performance: 'анализ CPA и конверсий',
    zero_conversion_investigation: 'расследование расхода без конверсий',
    traffic_proxy: 'анализ качества трафика без CPA',
    sample_extension: 'анализ трафика и расширение выборки',
    no_delivery: 'проверка статуса и настроек',
  },

  // Safe error/reason codes, mirroring backend SAFE_ERROR_MESSAGES.
  errorCode: {
    direct_auth_error: 'Нужно переподключить аккаунт Яндекса.',
    direct_permission_denied: 'У аккаунта недостаточно прав для чтения этих данных.',
    direct_rate_limited: 'Яндекс временно ограничил частоту запросов.',
    direct_report_processing: 'Отчёт Яндекс.Директа ещё формируется.',
    direct_report_queue_full: 'Очередь отчётов Яндекса заполнена. Следующая попытка будет выполнена автоматически.',
    direct_report_queue_full_timeout: 'Очередь отчётов Яндекса не освободилась за безопасное время ожидания.',
    direct_report_failed: 'Яндекс.Директ не сформировал отчёт.',
    direct_invalid_field_combination: 'Набор показателей не поддерживается для этого отчёта.',
    direct_no_data: 'За выбранный период данных нет.',
    capability_not_supported: 'Этот срез пока не поддерживается.',
    capability_not_applicable: 'Этот срез неприменим к типу кампании.',
    hypothesis_type_capability_mismatch: 'Запрос не соответствует проверяемой гипотезе.',
    untrusted_fact_binding: 'Гипотеза отклонена: нет доверенного исходного факта той же кампании.',
    unknown_conversion_metric: 'Данные по конверсиям отсутствуют или некорректны.',
    saved_fallback_used: 'Использованы сохранённые данные вместо live-отчёта.',
    cache_miss: 'Подходящих данных в кеше нет.',
    provider_timeout: 'AI-провайдер не ответил вовремя.',
    json_schema_validation_failed: 'Ответ AI не прошёл проверку формата.',
  },

  // State of the last data synchronisation for a client.
  syncStatus: {
    never_synced: 'Ещё не запускалась',
    pending: 'Ожидает',
    running: 'В процессе',
    loading: 'Загрузка',
    completed: 'Завершено',
    success: 'Завершено',
    ok: 'Завершено',
    ready: 'Готово',
    failed: 'Ошибка',
    error: 'Ошибка',
    no_data: 'Данных нет',
    no_connection: 'Нет подключения',
  },

  // Short badge text shared by readiness cards and draft actions.
  compactStatus: {
    ready: 'Готово',
    action_needed: 'Нужно действие',
    blocked: 'Блокер',
    pending: 'Нет данных',
    loading: 'Загрузка',
    error: 'Ошибка',
    draft: 'Черновик',
    reviewed: 'Просмотрено',
    approved: 'Одобрено',
    rejected: 'Отклонено',
    needs_changes: 'Нужны правки',
  },

  journalSource: {
    ai: 'AI',
    optimization: 'Оптимизация',
    integration: 'Интеграции',
    sync: 'Синхронизация',
    business_context: 'Контекст бизнеса',
    client: 'Клиент',
    system: 'Система',
  },

  journalCategory: {
    recommendation: 'Рекомендация',
    action: 'Действие',
    status: 'Статус',
    data_change: 'Изменение данных',
    error: 'Ошибка',
    note: 'Заметка',
  },

  journalSeverity: {
    info: 'Инфо',
    success: 'Успех',
    warning: 'Внимание',
    error: 'Ошибка',
  },

  journalEventType: {
    'client.selected': 'Выбран клиент',
    'client.created': 'Клиент создан',
    'client.updated': 'Клиент изменён',
    'optimization.action_status_changed': 'Изменён статус действия',
    'integration.yandex_account_bound': 'Аккаунт Яндекса привязан',
    'integration.yandex_account_unbound': 'Аккаунт Яндекса отвязан',
    'integration.yandex_updated': 'Интеграция с Яндексом обновлена',
    'sync.started': 'Синхронизация запущена',
    'sync.completed': 'Синхронизация завершена',
    'sync.failed': 'Ошибка синхронизации',
  },

  // What DirectPilot proposes to do. Every action stays read-only until approved.
  optimizationActionType: {
    manual_review: 'Проверить вручную',
    add_negative_keywords: 'Добавить минус-слова',
  },

  // What the proposed action applies to.
  optimizationEntityType: {
    campaign: 'кампания',
    ad_group: 'группа объявлений',
    keyword: 'ключевая фраза',
    search_query: 'поисковый запрос',
    account: 'аккаунт',
  },

  // Why a draft action was raised.
  optimizationCategory: {
    conversion_efficiency: 'Эффективность конверсий',
    search_query_negative_keywords: 'Минус-слова по поисковым запросам',
  },

  optimizationStatus: {
    draft: 'Черновик',
    reviewed: 'Просмотрено',
    approved: 'Одобрено',
    rejected: 'Отклонено',
    needs_changes: 'Нужны правки',
    applied: 'Применено',
  },
});

/**
 * Human label for a code, or `null` when the code is unknown.
 * Never returns the raw code — that is the whole point of this module.
 */
export function labelFor(group, code) {
  if (code === null || code === undefined) return null;
  const dictionary = LABEL_GROUPS[group];
  if (!dictionary) return null;
  const label = dictionary[String(code)];
  return label || null;
}

export function hasLabel(group, code) {
  return labelFor(group, code) !== null;
}

/** Human label, or a dash when the code is unknown or missing. */
export function labelOrDash(group, code, dash = '—') {
  return labelFor(group, code) ?? dash;
}

/**
 * Translate a list of codes, silently dropping the ones with no label.
 * Used where an unknown code should disappear rather than show as a dash.
 */
export function labelList(group, codes) {
  if (!Array.isArray(codes)) return [];
  return codes.map((code) => labelFor(group, code)).filter(Boolean);
}

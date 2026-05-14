from app.schemas import (
    AffectedItem,
    AgencyMetric,
    AuditIssue,
    Campaign,
    ClientSummary,
    IntegrationStatus,
    Recommendation,
    RecommendationDiff,
)

CLIENTS = [
    ClientSummary(
        id="furniture",
        name="Интернет-магазин мебели",
        segment="E-commerce",
        spend="184 200 ₽",
        leads=142,
        cpa="1 297 ₽",
        roas="428%",
        trend="CPA −12%",
        score=74,
        status="Требует внимания",
    ),
    ClientSummary(
        id="dentistry",
        name="Стоматология Премиум",
        segment="Медицина",
        spend="96 800 ₽",
        leads=63,
        cpa="1 536 ₽",
        roas="312%",
        trend="Лиды +9%",
        score=82,
        status="Стабильно",
    ),
    ClientSummary(
        id="school",
        name="Онлайн-школа английского",
        segment="EdTech",
        spend="128 400 ₽",
        leads=218,
        cpa="589 ₽",
        roas="356%",
        trend="CTR +18%",
        score=88,
        status="Рост",
    ),
]

AGENCY_METRICS = [
    AgencyMetric(label="Клиентов под контролем", value="24", delta="+3 за месяц"),
    AgencyMetric(label="Расход за 30 дней", value="4,8 млн ₽", delta="−7% к плану"),
    AgencyMetric(label="AI-рекомендаций", value="186", delta="42 высокого приоритета"),
    AgencyMetric(label="Потенциал экономии", value="612 тыс ₽", delta="по read-only аудиту"),
]

CAMPAIGNS = [
    Campaign(name="Поиск | Москва | Мебель", spend="74 200 ₽", leads=61, cpa="1 216 ₽", status="Активна"),
    Campaign(name="РСЯ | Широкие интересы", spend="48 700 ₽", leads=0, cpa="—", status="Проблема"),
    Campaign(name="Бренд | РФ", spend="22 600 ₽", leads=44, cpa="514 ₽", status="Ограничена бюджетом"),
    Campaign(name="Ретаргетинг | Корзина", spend="18 900 ₽", leads=21, cpa="900 ₽", status="Активна"),
]

AUDIT_ISSUES = [
    AuditIssue(
        priority="high",
        title="Расход без конверсий в РСЯ",
        object="РСЯ | Широкие интересы | Мебель",
        evidence="48 700 ₽ за 14 дней, 0 целей Метрики, CPC выше среднего на 23%.",
        action="Ограничить бюджет и вынести запросы в отдельную проверку.",
    ),
    AuditIssue(
        priority="high",
        title="Не все кампании связаны с целями Метрики",
        object="4 кампании клиента",
        evidence="ИИ не может корректно считать CPA и обучать рекомендации без целей.",
        action="Проверить цели: заявка, звонок, корзина, покупка.",
    ),
    AuditIssue(
        priority="medium",
        title="Слабые объявления в поиске",
        object="12 объявлений",
        evidence="CTR ниже медианы аккаунта на 31%, нет явного УТП в заголовке.",
        action="Сгенерировать 2–3 варианта заголовков и запустить A/B-тест.",
    ),
]

RECOMMENDATIONS = [
    Recommendation(
        id="pause-wasted-keywords",
        risk="Низкий",
        impact="−9–12% расходов",
        title="Остановить 12 ключей без конверсий",
        reason="Ключи потратили 48 700 ₽ за 14 дней и не принесли целевых действий.",
        objects="12 ключей · 3 группы · 2 кампании",
        mode="Можно применить после подтверждения",
        status="new",
        evidence=["Расход: 48 700 ₽", "Конверсии: 0", "Период анализа: 14 дней", "Целевой CPA: 1 300 ₽"],
        affected_items=[
            AffectedItem(
                type="Ключ",
                name="купить диван недорого",
                campaign="Поиск | Москва | Мебель",
                spend="8 400 ₽",
                conversions=0,
                action="Остановить",
            ),
            AffectedItem(
                type="Ключ",
                name="мебель своими руками чертеж",
                campaign="РСЯ | Широкие интересы",
                spend="6 900 ₽",
                conversions=0,
                action="Остановить",
            ),
        ],
        diff=RecommendationDiff(before="Статус ключей: активен", after="Статус ключей: остановлен"),
    ),
    Recommendation(
        id="add-negative-keywords",
        risk="Низкий",
        impact="+6% CTR",
        title="Добавить 38 минус-фраз",
        reason="В поисковых запросах найден нерелевантный трафик с информационным интентом.",
        objects="38 фраз · поиск и РСЯ",
        mode="Требуется просмотр списка фраз",
        status="approval_required",
        evidence=["38 запросов без коммерческого интента", "12 300 ₽ расхода", "CTR ниже среднего на 18%"],
        affected_items=[
            AffectedItem(
                type="Минус-фраза",
                name="своими руками",
                campaign="РСЯ | Широкие интересы",
                spend="3 100 ₽",
                conversions=0,
                action="Добавить",
            )
        ],
        diff=RecommendationDiff(before="Минус-фразы: базовый список", after="Минус-фразы: +38 новых фраз"),
    ),
]

INTEGRATIONS = [
    IntegrationStatus(
        id="yandex-direct",
        name="Яндекс.Директ",
        status="mock_connected",
        description="Будущий connector для кампаний, групп, объявлений, ключей, ставок и статистики.",
        next_action="Настроить OAuth-приложение и scopes.",
    ),
    IntegrationStatus(
        id="yandex-metrica",
        name="Яндекс.Метрика",
        status="mock_connected",
        description="Будущий connector для целей, ecommerce, атрибуции и качества лидов.",
        next_action="Связать цели Метрики с клиентскими KPI.",
    ),
    IntegrationStatus(
        id="crm",
        name="CRM / коллтрекинг",
        status="planned",
        description="Источник статусов лидов, продаж, выручки и маржи.",
        next_action="Выбрать первую CRM-интеграцию.",
    ),
]

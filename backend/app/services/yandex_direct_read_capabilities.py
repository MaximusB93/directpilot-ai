from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CampaignFamily = Literal["search", "yan", "unknown"]
SourceType = Literal["report", "service_get", "saved_data", "external"]

SEARCH_FAMILIES = frozenset({"search"})
YAN_FAMILIES = frozenset({"yan"})
KNOWN_FAMILIES = frozenset({"search", "yan"})
ALL_FAMILIES = frozenset({"search", "yan", "unknown"})
SEARCH_SUBTYPES = frozenset({"search", "brand_search"})
YAN_SUBTYPES = frozenset({"yan_prospecting", "yan_retargeting"})
KNOWN_SUBTYPES = SEARCH_SUBTYPES | YAN_SUBTYPES
ALL_SUBTYPES = KNOWN_SUBTYPES | frozenset({"unknown"})
PERFORMANCE_METRICS = (
    "impressions", "clicks", "cost", "ctr", "avg_cpc", "conversions", "cpa", "conversion_rate",
)
PERFORMANCE_FIELDS = (
    "Impressions", "Clicks", "Cost", "Ctr", "AvgCpc", "Conversions", "CostPerConversion", "ConversionRate",
)
OFFICIAL_REPORT_TYPES = frozenset({
    "ACCOUNT_PERFORMANCE_REPORT",
    "CAMPAIGN_PERFORMANCE_REPORT",
    "ADGROUP_PERFORMANCE_REPORT",
    "AD_PERFORMANCE_REPORT",
    "CRITERIA_PERFORMANCE_REPORT",
    "CUSTOM_REPORT",
    "REACH_AND_FREQUENCY_PERFORMANCE_REPORT",
    "SEARCH_QUERY_PERFORMANCE_REPORT",
})


@dataclass(frozen=True)
class DirectReadCapability:
    id: str
    title: str
    source_type: SourceType
    supported_families: frozenset[str]
    supported_subtypes: frozenset[str]
    allowed_dimensions: tuple[str, ...]
    allowed_metrics: tuple[str, ...]
    required_fields: tuple[str, ...] = ()
    incompatible_fields: tuple[tuple[str, str], ...] = ()
    allowed_filters: tuple[str, ...] = ("campaign_name",)
    default_limit: int = 200
    maximum_limit: int = 1000
    date_range_supported: bool = False
    goal_ids_supported: bool = False
    live_supported: bool = True
    read_only: bool = True
    cache_ttl_seconds: int = 900
    estimated_cost: str = "low"
    priority: int = 50
    service: str | None = None
    report_type: str | None = None
    api_fields: tuple[str, ...] = ()
    extra_params: tuple[tuple[str, tuple[str, ...]], ...] = ()
    source_required: str | None = None
    official_reference: str = ""


def _service(
    capability_id: str,
    title: str,
    service: str,
    fields: tuple[str, ...],
    metrics: tuple[str, ...],
    *,
    families: frozenset[str] = KNOWN_FAMILIES,
    subtypes: frozenset[str] = KNOWN_SUBTYPES,
    extra_params: tuple[tuple[str, tuple[str, ...]], ...] = (),
    limit: int = 1000,
    ttl: int = 3600,
) -> DirectReadCapability:
    return DirectReadCapability(
        capability_id, title, "service_get", families, subtypes, (capability_id,), metrics,
        default_limit=min(200, limit), maximum_limit=limit, cache_ttl_seconds=ttl,
        service=service, api_fields=fields, extra_params=extra_params,
        official_reference=f"Yandex Direct API v5 {service}.get",
    )


def _report(
    capability_id: str,
    title: str,
    report_type: str,
    fields: tuple[str, ...],
    metrics: tuple[str, ...] = PERFORMANCE_METRICS,
    *,
    families: frozenset[str] = KNOWN_FAMILIES,
    subtypes: frozenset[str] = KNOWN_SUBTYPES,
    goals: bool = True,
    limit: int = 1000,
    ttl: int = 900,
    cost: str = "medium",
    source_required: str | None = None,
) -> DirectReadCapability:
    return DirectReadCapability(
        capability_id, title, "report", families, subtypes, (capability_id,), metrics,
        required_fields=fields, default_limit=min(200, limit), maximum_limit=limit,
        date_range_supported=True, goal_ids_supported=goals, cache_ttl_seconds=ttl,
        estimated_cost=cost, report_type=report_type, api_fields=fields,
        source_required=source_required,
        official_reference=f"Yandex Direct Reports API {report_type}",
    )


_CAMPAIGN_FIELDS = ("Id", "Name", "Status", "State", "Type")
_AD_GROUP_FIELDS = ("Id", "CampaignId", "Name", "Status", "ServingStatus", "Type", "RegionIds", "NegativeKeywords")
_KEYWORD_FIELDS = ("Id", "CampaignId", "AdGroupId", "Keyword", "Status", "ServingStatus", "State", "StrategyPriority")
_AD_FIELDS = ("Id", "CampaignId", "AdGroupId", "Status", "State", "Type", "StatusClarification")
_TEXT_AD_FIELDS = ("Title", "Title2", "Text", "Href", "DisplayDomain", "Mobile", "SitelinkSetId", "AdExtensions")


YANDEX_DIRECT_READ_CAPABILITIES: dict[str, DirectReadCapability] = {
    "campaigns": _service("campaigns", "Кампании", "campaigns", _CAMPAIGN_FIELDS, ("name", "status", "state", "type"), families=ALL_FAMILIES, subtypes=ALL_SUBTYPES, limit=3000),
    "campaign_settings": _service("campaign_settings", "Настройки кампании", "campaigns", _CAMPAIGN_FIELDS, ("name", "status", "state", "type"), families=ALL_FAMILIES, subtypes=ALL_SUBTYPES),
    "campaign_status": _service("campaign_status", "Статус кампании", "campaigns", _CAMPAIGN_FIELDS, ("status", "state", "type"), families=ALL_FAMILIES, subtypes=ALL_SUBTYPES),
    "campaign_performance": _report("campaign_performance", "Эффективность кампании", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName") + PERFORMANCE_FIELDS),
    "campaign_daily_dynamics": _report("campaign_daily_dynamics", "Динамика кампании по дням", "CAMPAIGN_PERFORMANCE_REPORT", ("Date", "CampaignId", "CampaignName") + PERFORMANCE_FIELDS),
    "goals": _report("goals", "Конверсии по выбранным целям", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName") + PERFORMANCE_FIELDS),
    "conversions_by_goal": _report("conversions_by_goal", "Конверсии по целям", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName") + PERFORMANCE_FIELDS),
    "ad_groups": _service("ad_groups", "Группы объявлений", "adgroups", _AD_GROUP_FIELDS, ("name", "status", "serving_status", "type", "regions", "negative_keywords")),
    "ad_group_settings": _service("ad_group_settings", "Настройки групп", "adgroups", _AD_GROUP_FIELDS, ("name", "status", "serving_status", "type", "regions", "negative_keywords")),
    "ad_group_performance": _report("ad_group_performance", "Эффективность групп", "ADGROUP_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "AdGroupId", "AdGroupName") + PERFORMANCE_FIELDS),
    "keywords": _service("keywords", "Ключевые фразы", "keywords", _KEYWORD_FIELDS, ("keyword", "status", "serving_status", "state", "strategy_priority"), families=SEARCH_FAMILIES, subtypes=SEARCH_SUBTYPES),
    "autotargeting": _service("autotargeting", "Автотаргетинг", "keywords", _KEYWORD_FIELDS, ("keyword", "status", "serving_status", "state"), families=SEARCH_FAMILIES, subtypes=SEARCH_SUBTYPES),
    "keyword_performance": _report("keyword_performance", "Эффективность ключевых фраз", "CRITERIA_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "AdGroupId", "AdGroupName", "CriterionId", "Criterion", "CriterionType") + PERFORMANCE_FIELDS, families=SEARCH_FAMILIES, subtypes=SEARCH_SUBTYPES),
    "criteria_performance": _report("criteria_performance", "Эффективность критериев", "CRITERIA_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "AdGroupId", "AdGroupName", "CriterionId", "Criterion", "CriterionType") + PERFORMANCE_FIELDS),
    "search_queries": _report("search_queries", "Поисковые запросы", "SEARCH_QUERY_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "AdGroupId", "AdGroupName", "Query") + PERFORMANCE_FIELDS, families=SEARCH_FAMILIES, subtypes=SEARCH_SUBTYPES, cost="high"),
    "ads": _service("ads", "Объявления", "ads", _AD_FIELDS, ("status", "state", "type", "status_clarification"), extra_params=(("TextAdFieldNames", _TEXT_AD_FIELDS),)),
    "ad_texts": _service("ad_texts", "Тексты объявлений", "ads", _AD_FIELDS, ("title", "title2", "text"), extra_params=(("TextAdFieldNames", _TEXT_AD_FIELDS),)),
    "ad_urls": _service("ad_urls", "Ссылки объявлений", "ads", _AD_FIELDS, ("href", "display_domain"), extra_params=(("TextAdFieldNames", _TEXT_AD_FIELDS),)),
    "creatives": _service("creatives", "Креативы объявлений", "ads", _AD_FIELDS, ("type", "status", "state"), extra_params=(("TextAdFieldNames", _TEXT_AD_FIELDS),)),
    "sitelinks": _service("sitelinks", "Быстрые ссылки", "ads", _AD_FIELDS, ("sitelink_set",), extra_params=(("TextAdFieldNames", _TEXT_AD_FIELDS),)),
    "callouts": _service("callouts", "Уточнения", "ads", _AD_FIELDS, ("ad_extensions",), extra_params=(("TextAdFieldNames", _TEXT_AD_FIELDS),)),
    "ad_performance": _report("ad_performance", "Эффективность объявлений", "AD_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "AdGroupId", "AdGroupName", "AdId") + PERFORMANCE_FIELDS),
    "audience_targets": _service("audience_targets", "Аудиторные таргетинги", "audiencetargets", ("Id", "AdGroupId", "RetargetingListId", "State", "StrategyPriority"), ("state", "strategy_priority"), families=YAN_FAMILIES, subtypes=YAN_SUBTYPES),
    "retargeting_lists": _service("retargeting_lists", "Списки ретаргетинга", "retargetinglists", ("Id", "Type", "Name", "Description", "Rules", "IsAvailable", "Scope"), ("type", "name", "description", "rules", "is_available", "scope"), families=YAN_FAMILIES, subtypes=YAN_SUBTYPES),
    "retargeting_segments": _service("retargeting_segments", "Сегменты ретаргетинга", "retargetinglists", ("Id", "Type", "Name", "Description", "Rules", "IsAvailable", "Scope"), ("type", "name", "rules", "is_available", "scope"), families=YAN_FAMILIES, subtypes=frozenset({"yan_retargeting"})),
    "campaign_bid_modifiers": _service("campaign_bid_modifiers", "Корректировки кампании", "bidmodifiers", ("Id", "CampaignId", "AdGroupId", "Level", "Type"), ("level", "type")),
    "bid_modifiers": _service("bid_modifiers", "Корректировки ставок", "bidmodifiers", ("Id", "CampaignId", "AdGroupId", "Level", "Type"), ("level", "type")),
    "devices": _report("devices", "Устройства", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "Device") + PERFORMANCE_FIELDS),
    "geo": _report("geo", "География присутствия", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "LocationOfPresenceId", "LocationOfPresenceName") + PERFORMANCE_FIELDS),
    "location_of_presence": _report("location_of_presence", "География присутствия", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "LocationOfPresenceId", "LocationOfPresenceName") + PERFORMANCE_FIELDS),
    "demographics": _report("demographics", "Демография", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "Age", "Gender") + PERFORMANCE_FIELDS),
    "age": _report("age", "Возраст", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "Age") + PERFORMANCE_FIELDS),
    "gender": _report("gender", "Пол", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "Gender") + PERFORMANCE_FIELDS),
    "placement_or_network_breakdown": _report("placement_or_network_breakdown", "Площадки и сети", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "AdNetworkType", "Placement", "ExternalNetworkName") + PERFORMANCE_FIELDS, families=YAN_FAMILIES, subtypes=YAN_SUBTYPES),
    "placements": _report("placements", "Площадки", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "Placement", "ExternalNetworkName") + PERFORMANCE_FIELDS, families=YAN_FAMILIES, subtypes=YAN_SUBTYPES),
    "ad_format": _report("ad_format", "Форматы объявлений", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "AdFormat") + PERFORMANCE_FIELDS),
    "mobile_platform": _report("mobile_platform", "Мобильные платформы", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "MobilePlatform") + PERFORMANCE_FIELDS),
    "carrier": _report("carrier", "Тип подключения", "CUSTOM_REPORT", ("CampaignId", "CampaignName", "CarrierType") + PERFORMANCE_FIELDS),
    "frequency_and_reach": _report("frequency_and_reach", "Охват и частота", "REACH_AND_FREQUENCY_PERFORMANCE_REPORT", ("CampaignId", "Impressions", "ImpressionReach", "AvgImpressionFrequency"), ("impressions", "impression_reach", "avg_impression_frequency"), families=YAN_FAMILIES, subtypes=YAN_SUBTYPES, goals=False),
    "frequency": _report("frequency", "Охват и частота", "REACH_AND_FREQUENCY_PERFORMANCE_REPORT", ("CampaignId", "Impressions", "ImpressionReach", "AvgImpressionFrequency"), ("impressions", "impression_reach", "avg_impression_frequency"), families=YAN_FAMILIES, subtypes=YAN_SUBTYPES, goals=False),
    "conversion_rate": _report("conversion_rate", "Коэффициент конверсии", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "Clicks", "Conversions", "ConversionRate"), ("clicks", "conversions", "conversion_rate"), source_required="metrika"),
    "cost_per_conversion": _report("cost_per_conversion", "Стоимость конверсии", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "Cost", "Conversions", "CostPerConversion"), ("cost", "conversions", "cpa"), source_required="metrika"),
    "revenue": _report("revenue", "Доход по целям", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "Conversions", "Revenue"), ("conversions", "revenue"), source_required="metrika"),
    "roi": _report("roi", "ROI по целям", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "Cost", "Revenue", "GoalsRoi"), ("cost", "revenue", "roi"), source_required="metrika"),
    "pageviews": _report("pageviews", "Глубина просмотра", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "Clicks", "AvgPageviews"), ("clicks", "pageviews"), source_required="metrika"),
    "bounce_rate": _report("bounce_rate", "Показатель отказов", "CAMPAIGN_PERFORMANCE_REPORT", ("CampaignId", "CampaignName", "Clicks", "Bounces", "BounceRate"), ("clicks", "bounces", "bounce_rate"), source_required="metrika"),
}


def _unavailable(capability_id: str, title: str, source_required: str) -> DirectReadCapability:
    return DirectReadCapability(
        capability_id, title, "external", KNOWN_FAMILIES, KNOWN_SUBTYPES, (capability_id,), (),
        live_supported=False, source_required=source_required, official_reference="External source; not Direct API data",
    )


for _item in (
    _unavailable("landing_pages", "Содержимое посадочных страниц", "page_analyzer"),
    _unavailable("lead_quality", "Качество лидов", "crm"),
    _unavailable("conversion_sources", "Источники конверсий", "metrika"),
    _unavailable("audience_exclusions", "Исключения аудиторий", "direct_campaign_settings"),
    _unavailable("images", "Изображения", "direct_creative_metadata"),
    _unavailable("videos", "Видео", "direct_creative_metadata"),
    _unavailable("campaign_strategy", "Стратегия кампании", "direct_campaign_type_fields"),
    _unavailable("targeting_conditions", "Условия таргетинга", "direct_campaign_type_fields"),
    _unavailable("account_summary", "Сводка аккаунта", "direct_account_report"),
):
    YANDEX_DIRECT_READ_CAPABILITIES[_item.id] = _item


def public_direct_read_manifest() -> list[dict[str, object]]:
    """Expose semantic capabilities only; API services and raw fields stay backend-only."""

    return [
        {
            "id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "supported_campaign_families": sorted(item.supported_families),
            "supported_campaign_subtypes": sorted(item.supported_subtypes),
            "permitted_metrics": list(item.allowed_metrics),
            "maximum_rows": item.maximum_limit,
            "date_range_supported": item.date_range_supported,
            "goal_ids_supported": item.goal_ids_supported,
            "supported_now": item.live_supported,
            "source_required": item.source_required,
            "read_only": True,
        }
        for item in YANDEX_DIRECT_READ_CAPABILITIES.values()
    ]


def get_direct_read_capabilities(
    *,
    campaign_family: str | None = None,
    campaign_subtype: str | None = None,
) -> list[DirectReadCapability]:
    capabilities = list(YANDEX_DIRECT_READ_CAPABILITIES.values())
    if campaign_family:
        capabilities = [item for item in capabilities if campaign_family in item.supported_families]
    if campaign_subtype:
        capabilities = [item for item in capabilities if campaign_subtype in item.supported_subtypes]
    return sorted(capabilities, key=lambda item: (item.priority, item.id))


def validate_capability_definition(capability: DirectReadCapability) -> None:
    if not capability.read_only:
        raise ValueError("Direct capability must be read-only")
    if capability.source_type == "report":
        if capability.report_type not in OFFICIAL_REPORT_TYPES:
            raise ValueError("Unsupported Yandex Direct report type")
        if not capability.api_fields or not set(capability.required_fields).issubset(capability.api_fields):
            raise ValueError("Invalid report field definition")
        for left, right in capability.incompatible_fields:
            if left in capability.api_fields and right in capability.api_fields:
                raise ValueError("Incompatible report fields")
    if capability.source_type == "service_get" and not capability.service:
        raise ValueError("Object capability must define an allowlisted service")

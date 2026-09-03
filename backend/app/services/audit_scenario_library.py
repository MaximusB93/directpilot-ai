from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.audit_evidence import parse_numeric_metric


ConversionDataState = Literal[
    "known_positive",
    "known_zero",
    "unknown",
    "low_sample",
    "not_applicable",
]
AnalysisMode = Literal[
    "conversion_performance",
    "zero_conversion_investigation",
    "traffic_proxy",
    "sample_extension",
    "no_delivery",
]

SCENARIO_LIBRARY_VERSION = "2026-08-09.1"


@dataclass(frozen=True)
class ConversionStateDecision:
    state: ConversionDataState
    reason: str
    metric_state: Literal["known", "missing", "invalid"]


@dataclass(frozen=True)
class AuditScenario:
    scenario_id: str
    title: str
    analysis_mode: AnalysisMode
    must_analyze: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    next_data: tuple[str, ...]

    def public_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_version": SCENARIO_LIBRARY_VERSION,
            "title": self.title,
            "analysis_mode": self.analysis_mode,
            "must_analyze": list(self.must_analyze),
            "forbidden_claims": list(self.forbidden_claims),
            "next_data": list(self.next_data),
        }


_UNKNOWN_BY_CAMPAIGN_TYPE: dict[str, AuditScenario] = {
    "search": AuditScenario(
        scenario_id="search_unknown_conversions",
        title="Поиск без достоверной конверсионной метрики",
        analysis_mode="traffic_proxy",
        must_analyze=(
            "search_queries", "keywords", "autotargeting", "ads", "devices", "geo",
        ),
        forbidden_claims=(
            "кампания не приносит конверсий", "CPA выше цели", "сегмент не приносит продажи",
        ),
        next_data=("goals", "search_queries", "devices", "geo"),
    ),
    "yan": AuditScenario(
        scenario_id="yan_unknown_conversions",
        title="РСЯ без достоверной конверсионной метрики",
        analysis_mode="traffic_proxy",
        must_analyze=("placements", "audience_targets", "ads", "devices", "geo", "frequency"),
        forbidden_claims=(
            "кампания не приносит конверсий", "CPA выше цели", "площадка не приносит продажи",
        ),
        next_data=("goals", "placements", "audience_targets", "frequency"),
    ),
    "retargeting": AuditScenario(
        scenario_id="retargeting_unknown_conversions",
        title="Ретаргетинг без достоверной конверсионной метрики",
        analysis_mode="traffic_proxy",
        must_analyze=(
            "retargeting_segments", "audience_targets", "placements", "ads", "devices", "geo", "frequency",
        ),
        forbidden_claims=(
            "ретаргетинг не приносит конверсий", "CPA выше цели", "аудитория не приносит продажи",
        ),
        next_data=("goals", "retargeting_segments", "placements", "frequency"),
    ),
    "unknown": AuditScenario(
        scenario_id="unclassified_unknown_conversions",
        title="Кампания неизвестного типа без достоверной конверсионной метрики",
        analysis_mode="traffic_proxy",
        must_analyze=("campaign_settings", "campaigns", "goals"),
        forbidden_claims=("кампания не приносит конверсий", "CPA выше цели"),
        next_data=("campaign_settings", "goals"),
    ),
}

_STATE_SCENARIOS: dict[ConversionDataState, AuditScenario] = {
    "known_positive": AuditScenario(
        scenario_id="known_positive_conversions",
        title="Конверсионный анализ по достоверной метрике",
        analysis_mode="conversion_performance",
        must_analyze=("campaign_performance", "devices", "geo"),
        forbidden_claims=(),
        next_data=("devices", "geo"),
    ),
    "known_zero": AuditScenario(
        scenario_id="known_zero_conversions",
        title="Расследование достоверного нуля конверсий",
        analysis_mode="zero_conversion_investigation",
        must_analyze=("campaign_performance", "goals", "devices", "geo"),
        forbidden_claims=("конверсионная метрика отсутствует",),
        next_data=("goals", "devices", "geo"),
    ),
    "low_sample": AuditScenario(
        scenario_id="known_conversions_low_sample",
        title="Расширение периода при малой выборке",
        analysis_mode="sample_extension",
        must_analyze=("campaign_performance", "campaign_dynamics", "devices", "geo"),
        forbidden_claims=("причина подтверждена", "сегмент необходимо исключить"),
        next_data=("campaign_dynamics", "devices", "geo"),
    ),
    "not_applicable": AuditScenario(
        scenario_id="no_delivery_in_period",
        title="Нет показов и расхода в анализируемом периоде",
        analysis_mode="no_delivery",
        must_analyze=("campaign_status", "campaign_settings"),
        forbidden_claims=("кампания неэффективна", "кампания не приносит конверсий"),
        next_data=("campaign_status", "campaign_settings"),
    ),
}


def classify_conversion_state(
    raw_value: Any,
    *,
    sufficient_data: bool,
    cost: float = 0,
    clicks: int = 0,
    impressions: int = 0,
) -> ConversionStateDecision:
    """Keep observed zero distinct from missing/invalid and from low sample."""

    metric = parse_numeric_metric(raw_value)
    if metric.state == "known" and cost <= 0 and clicks <= 0 and impressions <= 0:
        return ConversionStateDecision("not_applicable", "no_delivery_in_period", metric.state)
    if metric.state == "missing":
        return ConversionStateDecision("unknown", "conversion_metric_missing", metric.state)
    if metric.state == "invalid":
        return ConversionStateDecision("unknown", "conversion_metric_invalid", metric.state)
    if not sufficient_data:
        reason = "known_zero_low_sample" if metric.value == 0 else "known_positive_low_sample"
        return ConversionStateDecision("low_sample", reason, metric.state)
    if metric.value == 0:
        return ConversionStateDecision("known_zero", "observed_zero", metric.state)
    return ConversionStateDecision("known_positive", "observed_positive", metric.state)


def select_audit_scenario(
    *,
    campaign_type: str,
    conversion_state: ConversionDataState,
) -> AuditScenario:
    if conversion_state == "unknown":
        return _UNKNOWN_BY_CAMPAIGN_TYPE.get(campaign_type, _UNKNOWN_BY_CAMPAIGN_TYPE["unknown"])
    if conversion_state == "low_sample":
        campaign_key = campaign_type if campaign_type in _UNKNOWN_BY_CAMPAIGN_TYPE else "unknown"
        traffic_scenario = _UNKNOWN_BY_CAMPAIGN_TYPE[campaign_key]
        base = _STATE_SCENARIOS["low_sample"]
        return AuditScenario(
            scenario_id=f"{campaign_key}_low_sample",
            title="Анализ трафика при малой конверсионной выборке",
            analysis_mode="sample_extension",
            must_analyze=tuple(dict.fromkeys(
                base.must_analyze + traffic_scenario.must_analyze
            )),
            forbidden_claims=tuple(dict.fromkeys(
                base.forbidden_claims
                + (
                    "CPA является устойчивым по одной-двум конверсиям",
                    "отклонение CTR или CPC доказывает влияние на продажи",
                )
            )),
            next_data=tuple(dict.fromkeys(
                base.next_data + traffic_scenario.next_data
            )),
        )
    return _STATE_SCENARIOS[conversion_state]

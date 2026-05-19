from dataclasses import dataclass

from app.schemas import AuditIssue


@dataclass(frozen=True)
class CampaignKpi:
    name: str
    spend: float
    clicks: int
    conversions: float
    ctr: float
    avg_cpc: float

    @property
    def cpa(self) -> float | None:
        if self.conversions <= 0:
            return None
        return self.spend / self.conversions


def build_audit_issues(campaigns: list[CampaignKpi], *, target_cpa: float = 1300.0) -> list[AuditIssue]:
    if not campaigns:
        return []

    issues: list[AuditIssue] = []
    avg_ctr = sum(item.ctr for item in campaigns) / len(campaigns)
    avg_cpc = sum(item.avg_cpc for item in campaigns) / len(campaigns)

    for item in campaigns:
        if item.spend >= 1000 and item.conversions <= 0:
            issues.append(
                AuditIssue(
                    priority="high",
                    title="Расход без конверсий",
                    object=item.name,
                    evidence=f"Расход {item.spend:.2f} ₽, конверсии {item.conversions:.2f}.",
                    action="Ограничить бюджет кампании и проверить поисковые запросы/минус-фразы.",
                )
            )

        cpa = item.cpa
        if cpa is not None and cpa > target_cpa * 1.3:
            issues.append(
                AuditIssue(
                    priority="high",
                    title="CPA сильно выше целевого",
                    object=item.name,
                    evidence=f"Фактический CPA {cpa:.2f} ₽ при целевом {target_cpa:.2f} ₽.",
                    action="Снизить ставки по слабым сегментам и проверить корректность целей Метрики.",
                )
            )

        if item.ctr > 0 and item.ctr < max(0.3, avg_ctr * 0.7):
            issues.append(
                AuditIssue(
                    priority="medium",
                    title="CTR ниже нормы аккаунта",
                    object=item.name,
                    evidence=f"CTR {item.ctr:.2f}% ниже 70% от среднего ({avg_ctr:.2f}%).",
                    action="Обновить тексты объявлений и запустить A/B тест креативов.",
                )
            )

        if item.avg_cpc > 0 and item.avg_cpc > avg_cpc * 1.25:
            issues.append(
                AuditIssue(
                    priority="medium",
                    title="CPC выше среднего",
                    object=item.name,
                    evidence=f"Avg CPC {item.avg_cpc:.2f} ₽ выше среднего {avg_cpc:.2f} ₽.",
                    action="Скорректировать ставки и отключить нерелевантные площадки/запросы.",
                )
            )

    low_data_count = sum(1 for item in campaigns if item.clicks < 20)
    if low_data_count:
        issues.append(
            AuditIssue(
                priority="low",
                title="Недостаточно данных по части кампаний",
                object=f"{low_data_count} кампаний",
                evidence="Кампании имеют менее 20 кликов за период; выводы по ним шумные.",
                action="Увеличить период анализа или объединить данные до принятия решений.",
            )
        )

    return issues

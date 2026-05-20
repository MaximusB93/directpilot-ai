from dataclasses import dataclass

from app.schemas import ChangePreview


@dataclass(frozen=True)
class PolicyVerdict:
    violations: list[str]
    risk_score: int


def evaluate_preview(preview: ChangePreview) -> PolicyVerdict:
    violations: list[str] = []
    risk_score = 0

    changed_objects = len(preview.changes)
    if changed_objects >= 20:
        violations.append("Слишком много изменений за один запуск (>20 объектов).")
        risk_score += 35
    elif changed_objects >= 10:
        risk_score += 20
    elif changed_objects >= 5:
        risk_score += 10

    if any("останов" in change.action.lower() for change in preview.changes):
        risk_score += 20
    if "бюджет" in preview.summary.lower():
        violations.append("Изменение бюджета требует отдельного подтверждения клиента.")
        risk_score += 30

    # normalize by recommendation risk hint
    hint = preview.risk.lower()
    if "выс" in hint:
        risk_score += 30
    elif "сред" in hint:
        risk_score += 15
    else:
        risk_score += 5

    return PolicyVerdict(violations=violations, risk_score=min(100, risk_score))

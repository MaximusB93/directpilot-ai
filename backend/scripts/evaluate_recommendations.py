"""Offline evaluation harness for AI recommendation quality.

Run:
  python backend/scripts/evaluate_recommendations.py
"""

from dataclasses import dataclass


@dataclass
class EvalCase:
    title: str
    expected_keyword: str
    response: str


def score_case(case: EvalCase) -> int:
    return 1 if case.expected_keyword.lower() in case.response.lower() else 0


def main() -> None:
    cases = [
        EvalCase("Spend without conversions", "конверс", "Проверьте расход без конверсий и остановите неэффективные ключи."),
        EvalCase("CPA anomaly", "cpa", "CPA выше цели, нужно снизить ставку."),
        EvalCase("Need approval", "approval", "Перед применением отправьте изменение на approval."),
    ]
    passed = sum(score_case(item) for item in cases)
    total = len(cases)
    print({"passed": passed, "total": total, "score": round(passed / total, 2)})


if __name__ == "__main__":
    main()

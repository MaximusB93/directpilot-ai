from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"

DOCUMENT_ORDER = [
    "direct_analysis_rules.md",
    "direct_budget_safety_rules.md",
    "direct_negative_keywords_rules.md",
    "direct_data_limitations.md",
    "direct_metrics_glossary.md",
]

KEYWORD_RULES: dict[str, tuple[str, ...]] = {
    "direct_analysis_rules.md": (
        "вчера",
        "сводка",
        "день",
        "кампан",
        "анализ",
        "ctr",
        "cpc",
        "cpa",
        "cr",
    ),
    "direct_budget_safety_rules.md": (
        "бюджет",
        "ставк",
        "расход",
        "bid",
        "budget",
        "сократить",
        "увеличить",
    ),
    "direct_negative_keywords_rules.md": (
        "минус",
        "поисковые запросы",
        "запросы",
        "negative",
        "keyword",
        "интент",
    ),
    "direct_data_limitations.md": (
        "нет данных",
        "не хватает",
        "огранич",
        "посадоч",
        "лендинг",
        "цели",
        "конверс",
        "динамик",
    ),
    "direct_metrics_glossary.md": (
        "cpa",
        "ctr",
        "cpc",
        "cr",
        "конверс",
        "показы",
        "клики",
        "роми",
        "romi",
        "дрр",
    ),
}


def _title_and_content(text: str, source: str) -> tuple[str, str]:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    title = source
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("#").strip()
        lines = lines[1:]
    content = "\n".join(line for line in lines if line.strip()).strip()
    return title, content


@lru_cache(maxsize=1)
def load_knowledge_documents() -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for source in DOCUMENT_ORDER:
        path = KNOWLEDGE_DIR / source
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        title, content = _title_and_content(text, source)
        documents.append({"source": source, "title": title, "content": content})
    return documents


def _text_from_context(context: dict[str, Any]) -> str:
    parts: list[str] = []
    client = context.get("client") or {}
    if isinstance(client, dict):
        parts.extend(str(value) for value in client.values() if value is not None)
    business_context = context.get("business_context") or {}
    if isinstance(business_context, dict):
        parts.append(str(business_context.get("status") or ""))
        fields = business_context.get("fields") or {}
        if isinstance(fields, dict):
            parts.extend(str(value) for value in fields.values() if value is not None)
    summary = context.get("summary") or {}
    if isinstance(summary, dict):
        parts.extend(str(key) for key in summary.keys())
    conversion_context = context.get("conversion_context") or {}
    if isinstance(conversion_context, dict):
        parts.extend(str(value) for value in conversion_context.values() if value is not None)
    return " ".join(parts).lower()


def _context_boosts(context: dict[str, Any]) -> dict[str, int]:
    boosts = {source: 0 for source in DOCUMENT_ORDER}

    business_context = context.get("business_context") or {}
    if isinstance(business_context, dict) and business_context.get("status") in {None, "", "empty"}:
        boosts["direct_data_limitations.md"] += 4

    conversion_context = context.get("conversion_context") or {}
    diagnostics = (
        context.get("syncDiagnostics")
        or context.get("sync_diagnostics")
        or conversion_context.get("sync_diagnostics")
        or {}
    )
    has_goal_data = conversion_context.get("has_goal_data")
    if has_goal_data is False or (isinstance(diagnostics, dict) and diagnostics.get("directGoalDataAvailable") is False):
        boosts["direct_data_limitations.md"] += 4
        boosts["direct_analysis_rules.md"] += 2

    search_query_insights = (
        context.get("searchQueryInsights")
        or context.get("search_query_insights")
        or (context.get("summary") or {}).get("searchQueryInsights")
    )
    if search_query_insights:
        boosts["direct_negative_keywords_rules.md"] += 4

    yesterday_summary = (
        context.get("yesterdayCampaignSummary")
        or context.get("yesterday_campaign_summary")
        or (context.get("summary") or {}).get("yesterdayCampaignSummary")
    )
    if yesterday_summary:
        boosts["direct_analysis_rules.md"] += 3
        boosts["direct_data_limitations.md"] += 1

    return boosts


def _shorten(content: str, max_chars: int = 900) -> str:
    normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def select_knowledge_snippets(query: str, context: dict[str, Any], limit: int = 5) -> list[dict[str, str]]:
    normalized_query = (query or "").lower()
    context_text = _text_from_context(context)
    combined = f"{normalized_query} {context_text}"
    boosts = _context_boosts(context)
    scored: list[tuple[int, int, dict[str, str]]] = []

    for index, document in enumerate(load_knowledge_documents()):
        source = document["source"]
        score = boosts.get(source, 0)
        for keyword in KEYWORD_RULES.get(source, ()):
            if keyword in combined:
                score += 2 if keyword in normalized_query else 1
        if score > 0:
            scored.append((score, -index, document))

    if not scored:
        scored = [
            (1, -DOCUMENT_ORDER.index(source), document)
            for source in ("direct_analysis_rules.md", "direct_data_limitations.md")
            for document in load_knowledge_documents()
            if document["source"] == source
        ]

    selected = sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[: max(1, min(limit, 5))]
    return [
        {
            "source": document["source"],
            "title": document["title"],
            "content": _shorten(document["content"]),
        }
        for _, _, document in selected
    ]
